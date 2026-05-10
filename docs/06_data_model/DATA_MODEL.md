# Verixa — Data Model & Schema

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 schema · Audience: Backend engineer, DBA, security architect, audit reviewer

---

## 1. Storage architecture overview

Verixa's persistent storage layer uses three concurrent stores:

- **Postgres 16 + pgvector** — structured operational data, hash-chained audit ledger, Trust Graph (via Apache AGE extension or Neo4j for very large deployments). Primary OLTP store.
- **Object store (S3-compatible / MinIO)** — Replay Vault snapshot bundles. Immutable, encrypted, content-addressable.
- **Redis** — short-lived: rate-limit counters, OPA decision cache (5-second TTL), Celery queue, escalation status cache.

This document specifies the Postgres schemas. The Replay Vault object-store layout and Redis key patterns are documented separately (referenced inline).

---

## 2. Schema groups

Postgres schemas are organised into eight logical groups, each in its own Postgres schema namespace:

| Schema | Purpose | Phase |
|---|---|---|
| `verixa_registry` | Agents, workflows, models, tools | 1 |
| `verixa_policy` | Rego policies and policy versions | 1 |
| `verixa_runtime` | Active runtime state (in-flight escalations, rate limits) | 1 |
| `verixa_audit` | Hash-chained audit ledger | 1 |
| `verixa_replay` | Replay Vault index (binary bundles in object store) | 1 |
| `verixa_review` | Triad reviews, human reviews | 1 |
| `verixa_dossier` | Compliance Dossier records | 1 |
| `verixa_trust_graph` | Trust Graph (Apache AGE on Postgres) | 4 |

Each schema has explicit `READ`, `WRITE`, and `ADMIN` Postgres roles; the application layer uses connection pools with role-specific credentials per use case.

---

## 3. Registry schema (`verixa_registry`)

### 3.1 `agents` — registered AI agents

```sql
CREATE TABLE verixa_registry.agents (
    agent_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    spiffe_id           TEXT UNIQUE NOT NULL,
    display_name        TEXT NOT NULL,
    role                TEXT NOT NULL,
    workflow_ids        UUID[] NOT NULL DEFAULT '{}',
    primary_model       TEXT,
    primary_model_hash  TEXT,
    sdk_version         TEXT,
    risk_baseline       NUMERIC(4,3) DEFAULT 0.500,
    metadata            JSONB DEFAULT '{}',
    is_active           BOOLEAN DEFAULT TRUE,
    registered_at       TIMESTAMPTZ DEFAULT NOW(),
    deactivated_at      TIMESTAMPTZ,
    created_by          TEXT NOT NULL,
    tenant_id           UUID NOT NULL
);

CREATE INDEX idx_agents_tenant_active ON verixa_registry.agents (tenant_id, is_active);
CREATE INDEX idx_agents_spiffe ON verixa_registry.agents (spiffe_id);
CREATE INDEX idx_agents_workflow_ids ON verixa_registry.agents USING GIN (workflow_ids);
```

### 3.2 `workflows` — registered workflows

```sql
CREATE TABLE verixa_registry.workflows (
    workflow_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    description         TEXT,
    risk_classification TEXT NOT NULL CHECK (risk_classification IN ('low', 'medium', 'high', 'critical')),
    sector              TEXT NOT NULL,
    compliance_packs    TEXT[] NOT NULL DEFAULT '{}',
    triad_policy_id     UUID REFERENCES verixa_policy.policies(policy_id),
    escalation_policy_id UUID REFERENCES verixa_policy.policies(policy_id),
    retention_tier      TEXT DEFAULT 'enterprise_production',
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    created_by          TEXT NOT NULL,
    tenant_id           UUID NOT NULL
);

CREATE INDEX idx_workflows_tenant_active ON verixa_registry.workflows (tenant_id, is_active);
CREATE INDEX idx_workflows_sector ON verixa_registry.workflows (sector);
```

### 3.3 `tools` — registered tool schemas

```sql
CREATE TABLE verixa_registry.tools (
    tool_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    schema              JSONB NOT NULL,
    risk_baseline       NUMERIC(4,3) DEFAULT 0.500,
    sensitive_arguments TEXT[] NOT NULL DEFAULT '{}',
    allowed_workflow_ids UUID[] NOT NULL DEFAULT '{}',
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    tenant_id           UUID NOT NULL,
    UNIQUE (tenant_id, name)
);
```

### 3.4 `models` — registered models (primary and reviewer)

```sql
CREATE TABLE verixa_registry.models (
    model_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    family              TEXT NOT NULL,
    version_hash        TEXT NOT NULL,
    role                TEXT NOT NULL CHECK (role IN ('primary', 'reviewer', 'verifier')),
    deployment_target   TEXT NOT NULL,
    quantisation        TEXT,
    full_precision      BOOLEAN DEFAULT FALSE,
    parameters_billion  NUMERIC(5,1),
    metadata            JSONB DEFAULT '{}',
    is_active           BOOLEAN DEFAULT TRUE,
    registered_at       TIMESTAMPTZ DEFAULT NOW(),
    tenant_id           UUID NOT NULL,
    UNIQUE (tenant_id, name, version_hash)
);
```

---

## 4. Policy schema (`verixa_policy`)

### 4.1 `policies` — Rego policies with versioning

```sql
CREATE TABLE verixa_policy.policies (
    policy_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    description         TEXT,
    rego_source         TEXT NOT NULL,
    rego_compiled_hash  TEXT NOT NULL,
    version             INTEGER NOT NULL DEFAULT 1,
    is_active           BOOLEAN DEFAULT TRUE,
    compliance_pack     TEXT,
    regulatory_mappings JSONB NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    created_by          TEXT NOT NULL,
    tenant_id           UUID NOT NULL,
    UNIQUE (tenant_id, name, version)
);

CREATE INDEX idx_policies_tenant_active ON verixa_policy.policies (tenant_id, is_active);
CREATE INDEX idx_policies_pack ON verixa_policy.policies (compliance_pack);
```

### 4.2 `policy_test_fixtures` — test cases for policy validation

```sql
CREATE TABLE verixa_policy.policy_test_fixtures (
    fixture_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id           UUID NOT NULL REFERENCES verixa_policy.policies(policy_id),
    name                TEXT NOT NULL,
    input_payload       JSONB NOT NULL,
    expected_result     TEXT NOT NULL CHECK (expected_result IN ('pass', 'fail', 'abstain')),
    expected_reason     TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    tenant_id           UUID NOT NULL
);
```

---

## 5. Audit ledger schema (`verixa_audit`)

The audit ledger is the single most important schema in Verixa. Hash-chained, Ed25519-signed, append-only.

### 5.1 `audit_entries` — every governed action

```sql
CREATE TABLE verixa_audit.audit_entries (
    audit_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    sequence_number     BIGINT NOT NULL,
    event_time          TIMESTAMPTZ NOT NULL,

    -- subject of governance
    workflow_id         UUID NOT NULL,
    agent_id            UUID NOT NULL,
    action_type         TEXT NOT NULL,
    tool_name           TEXT,

    -- decision
    decision            TEXT NOT NULL CHECK (decision IN ('allow', 'deny', 'escalate', 'pending')),
    reason              TEXT,
    risk_score          NUMERIC(4,3),
    risk_classification TEXT,

    -- triad
    triad_invoked       BOOLEAN DEFAULT FALSE,
    triad_review_id     UUID,
    triad_consensus     TEXT,

    -- evidence
    snapshot_object_key TEXT,
    snapshot_hash       TEXT,

    -- hash chain
    hash_chain_prev     TEXT,
    hash_chain_self     TEXT NOT NULL,
    signature           TEXT NOT NULL,
    signing_key_id      TEXT NOT NULL,

    -- runtime metadata
    latency_ms          INTEGER,
    request_id          TEXT,
    trace_id            TEXT,

    -- regulatory mapping
    policies_applied    JSONB NOT NULL DEFAULT '[]',

    UNIQUE (tenant_id, sequence_number)
);

CREATE INDEX idx_audit_tenant_time ON verixa_audit.audit_entries (tenant_id, event_time DESC);
CREATE INDEX idx_audit_workflow ON verixa_audit.audit_entries (tenant_id, workflow_id, event_time DESC);
CREATE INDEX idx_audit_agent ON verixa_audit.audit_entries (tenant_id, agent_id, event_time DESC);
CREATE INDEX idx_audit_decision ON verixa_audit.audit_entries (tenant_id, decision);
CREATE INDEX idx_audit_risk_high ON verixa_audit.audit_entries (tenant_id, event_time DESC) WHERE risk_classification = 'high';
```

### 5.2 Hash-chain integrity

Per audit entry:
```
hash_chain_self = sha256(
    sequence_number || event_time || workflow_id || agent_id ||
    action_type || decision || risk_score ||
    snapshot_hash || hash_chain_prev
)

signature = ed25519_sign(signing_key, hash_chain_self)
```

For sequence_number = 0 (genesis): `hash_chain_prev = sha256("verixa-genesis-" || tenant_id)`.

Integrity verification walks the chain from any entry to genesis, validating each `hash_chain_self` against its inputs and verifying each signature against the corresponding signing key.

### 5.3 `signing_keys` — key registry

```sql
CREATE TABLE verixa_audit.signing_keys (
    key_id              TEXT PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    public_key_pem      TEXT NOT NULL,
    algorithm           TEXT NOT NULL DEFAULT 'ed25519',
    activated_at        TIMESTAMPTZ NOT NULL,
    deactivated_at      TIMESTAMPTZ,
    is_active           BOOLEAN DEFAULT TRUE
);
```

Private keys are stored in HashiCorp Vault, never in Postgres. Public keys in Postgres for verification.

---

## 6. Replay schema (`verixa_replay`)

### 6.1 `replay_index` — index for snapshot bundles in object store

```sql
CREATE TABLE verixa_replay.replay_index (
    replay_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id            UUID NOT NULL,
    tenant_id           UUID NOT NULL,
    object_key          TEXT NOT NULL,
    object_store_url    TEXT NOT NULL,
    bundle_hash         TEXT NOT NULL,
    encryption_key_id   TEXT NOT NULL,
    bundle_size_bytes   BIGINT,
    retention_tier      TEXT NOT NULL CHECK (retention_tier IN ('hot', 'warm', 'cold')),
    expires_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, audit_id)
);

CREATE INDEX idx_replay_audit ON verixa_replay.replay_index (audit_id);
CREATE INDEX idx_replay_retention ON verixa_replay.replay_index (tenant_id, retention_tier, expires_at);
```

### 6.2 Snapshot bundle layout (object store)

Each bundle is a tar.gz archive at `verixa-replay/{tenant_id}/{yyyy}/{mm}/{dd}/{audit_id}.tar.gz` containing:

- `manifest.json` — bundle metadata, bundle hash, encryption key ID
- `request.json` — the original governed-action request envelope
- `policy_evaluation.json` — every policy evaluated, inputs, results, traces
- `risk_evaluation.json` — risk engine inputs and output
- `triad/` — directory with per-reviewer commit-and-reveal payloads (if triad invoked)
- `evidence_validation.json` — evidence validator inputs and output (if invoked)
- `model_snapshots/` — model version hash references (not the model weights themselves; a hash pointer to the registered model in `verixa_registry.models`)
- `retrieved_documents/` — references to retrieved documents (hash + content if within size budget; otherwise hash + URL)
- `decision.json` — final decision record
- `hash_chain_record.json` — the audit ledger entry's hash chain position and signature

Bundles are encrypted with AES-256-GCM using a per-tenant key hierarchy. Decryption requires Vault access.

---

## 7. Review schema (`verixa_review`)

### 7.1 `triad_reviews` — Triad Review Engine records

```sql
CREATE TABLE verixa_review.triad_reviews (
    triad_review_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id            UUID NOT NULL,
    tenant_id           UUID NOT NULL,
    workflow_id         UUID NOT NULL,
    invoked_at          TIMESTAMPTZ DEFAULT NOW(),
    revealed_at         TIMESTAMPTZ,

    reviewer_a_model_id UUID NOT NULL,
    reviewer_b_model_id UUID NOT NULL,
    reviewer_c_model_id UUID NOT NULL,

    -- commit phase
    reviewer_a_commit_hash TEXT NOT NULL,
    reviewer_b_commit_hash TEXT NOT NULL,
    reviewer_c_commit_hash TEXT NOT NULL,
    commit_completed_at    TIMESTAMPTZ NOT NULL,

    -- reveal phase
    reviewer_a_verdict      TEXT,
    reviewer_a_reasoning    TEXT,
    reviewer_a_nonce        TEXT,
    reviewer_b_verdict      TEXT,
    reviewer_b_reasoning    TEXT,
    reviewer_b_nonce        TEXT,
    reviewer_c_verdict      TEXT,
    reviewer_c_reasoning    TEXT,
    reviewer_c_nonce        TEXT,

    consensus               TEXT,
    consensus_reason        TEXT,

    total_latency_ms        INTEGER,

    UNIQUE (tenant_id, audit_id)
);
```

### 7.2 `human_reviews` — Human Review Console records

```sql
CREATE TABLE verixa_review.human_reviews (
    human_review_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    escalation_id       UUID NOT NULL,
    audit_id            UUID NOT NULL,
    tenant_id           UUID NOT NULL,
    queued_at           TIMESTAMPTZ DEFAULT NOW(),
    assigned_at         TIMESTAMPTZ,
    decided_at          TIMESTAMPTZ,
    reviewer_identity   TEXT,
    reviewer_role       TEXT,
    decision            TEXT CHECK (decision IN ('approve', 'deny', 'request_more_info')),
    decision_notes      TEXT,
    review_duration_ms  INTEGER,
    sla_target_minutes  INTEGER,
    sla_breached        BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_human_reviews_tenant_status ON verixa_review.human_reviews (tenant_id, decided_at) WHERE decided_at IS NULL;
```

---

## 8. Dossier schema (`verixa_dossier`)

```sql
CREATE TABLE verixa_dossier.dossiers (
    dossier_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    workflow_id         UUID,
    time_range_start    TIMESTAMPTZ NOT NULL,
    time_range_end      TIMESTAMPTZ NOT NULL,
    regulator_target    TEXT,
    template_version    TEXT NOT NULL,
    pdf_object_key      TEXT NOT NULL,
    json_object_key     TEXT NOT NULL,
    hash_chain_proof    TEXT NOT NULL,
    summary             JSONB NOT NULL,
    generated_by        TEXT NOT NULL,
    generated_at        TIMESTAMPTZ DEFAULT NOW(),
    expires_at          TIMESTAMPTZ
);
```

---

## 9. Trust Graph schema (`verixa_trust_graph`, Phase 4+)

The Trust Graph is a property graph implemented via Apache AGE on Postgres for typical deployments (≤100M nodes, ≤500M edges) or Neo4j for very large enterprise deployments.

### Node labels

- `Workflow` — every governed workflow
- `Agent` — every registered agent
- `Model` — every model version (primary + reviewer)
- `Reviewer` — every human reviewer
- `Supplier` — third-party AI products and data sources
- `Incident` — every escalation, override, near-miss, breach
- `Decision` — selected high-significance decisions (not every action; that's the audit ledger)
- `PolicyVersion` — every Rego policy version

### Edge types

- `EXECUTED_BY` (Decision → Agent)
- `IN_WORKFLOW` (Decision → Workflow)
- `REVIEWED_BY` (Decision → Reviewer or Decision → Triad)
- `TRIGGERED_INCIDENT` (Decision → Incident)
- `USES_MODEL` (Agent → Model)
- `DEPENDS_ON_SUPPLIER` (Agent → Supplier or Workflow → Supplier)
- `OVERRIDDEN_BY` (Decision → Reviewer)
- `EVALUATED_AGAINST` (Decision → PolicyVersion)
- `RELATED_TO` (Incident → Incident — incident lineage)

### Trust Graph queries

Examples (in Cypher-equivalent for Apache AGE):
- Agent drift history: `MATCH (a:Agent {agent_id: $id})-[:USES_MODEL]->(m:Model) RETURN m ORDER BY m.activated_at`
- Workflow failure memory: `MATCH (d:Decision)-[:IN_WORKFLOW]->(w:Workflow {workflow_id: $id}) WHERE d.decision = 'deny' OR d.escalated = true RETURN d`
- Reviewer effectiveness: `MATCH (d:Decision)-[:REVIEWED_BY]->(r:Reviewer {reviewer_id: $id}) RETURN r.reviewer_id, count(d), avg(d.outcome_quality_score)`
- Supplier trust score: `MATCH (a:Agent)-[:DEPENDS_ON_SUPPLIER]->(s:Supplier {supplier_id: $id}) MATCH (d:Decision)-[:EXECUTED_BY]->(a) RETURN s, count(d), count(d) FILTER (WHERE d.triggered_incident IS NOT NULL)`

### Maintenance

The Trust Graph is updated asynchronously from the Audit Ledger by the `trust_graph_rollup` Celery job. Updates are idempotent. Rollup latency target: 60 seconds from audit entry to graph reflection.

---

## 10. Tenancy isolation

All tables include `tenant_id`. Tenant isolation is enforced at three layers:

1. **Row-level security (RLS)** — Postgres RLS policies on every table; application connection is bound to a tenant context that filters all queries
2. **Schema-level (single-tenant deployments)** — Tier 1, 2, 3 deployments use one Postgres instance per tenant; no cross-tenant data shares a database
3. **Application-level** — every API endpoint resolves tenant from authenticated identity; tenant ID is never accepted from request body

### RLS example

```sql
ALTER TABLE verixa_audit.audit_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_audit ON verixa_audit.audit_entries
    USING (tenant_id = current_setting('verixa.current_tenant')::UUID);
```

---

## 11. Retention and lifecycle

Retention policies operate at three levels:

1. **Hot tier** — Postgres primary + replicas. Default 90 days.
2. **Warm tier** — Postgres warm archive (compressed tablespace, slower indexes). Default 1–2 years.
3. **Cold tier** — Object store immutable evidence vault (Glacier / Azure Archive). Default 3–7 years sector-aligned.

Movement between tiers is handled by Celery jobs:
- `audit_warm_archive_mover` — moves rows older than retention threshold to warm tablespace
- `replay_cold_mover` — moves snapshot bundles to cold object store class
- `cold_legal_hold` — applies legal hold to specific objects

Deletion is opt-in per tenant per workflow per regulatory requirement. The default is "retain forever in cold tier". The customer's compliance team configures retention policy.

---

## 12. Migrations and schema evolution

- All schema changes go through Alembic migrations (Python ecosystem standard)
- Migrations are idempotent, reversible where possible, and tested in CI before production
- Schema evolution rule: never break the audit ledger hash chain; new columns are nullable and additive only on `audit_entries`
- Major version migrations get a Phase Gate review

---

*This Data Model document is the canonical schema reference for Verixa. The System Architecture Document references these tables. The Threat Model assesses tampering surfaces. Migration scripts live in the implementation repository under `migrations/`.*
