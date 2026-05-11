# Verixa — API Specification

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 API surface · Audience: Customer integration engineer, security architect, API reviewer

---

## 1. Overview

The Verixa API surface has three distinct API domains:

1. **Runtime API** — high-throughput, low-latency. Customer's AI agents call this for every governed action. OpenAI-compatible proxy variant + native Verixa variant.
2. **Control Plane API** — admin, configuration, query, replay, dossier. Used by operators, auditors, and the Verixa web UI.
3. **Webhook / Event API** — outbound notifications from Verixa to customer's SIEM, ITSM, ticketing, and approval-routing systems.

This document specifies all three at OpenAPI 3.1 stub level. The full OpenAPI YAML/JSON files are maintained alongside the implementation at `/api/openapi-runtime.yaml`, `/api/openapi-control.yaml`, and `/api/openapi-events.yaml` once code lands.

All three APIs use:
- **Authentication:** mTLS for service-to-service, OIDC bearer tokens for human users, API keys (rotated quarterly) for legacy integrations
- **Authorisation:** RBAC + Verixa policies (dogfooded — Verixa policies gate Verixa admin operations)
- **Versioning:** URI-prefixed (`/v1/...`); minor versions backward-compatible, major versions require migration
- **Rate limiting:** Per-tenant + per-API-key + per-endpoint; quotas defined in Pricing tier
- **Idempotency:** All POST endpoints accept `Idempotency-Key` header; replays of identical key return identical response within 24 hours

---

## 2. Runtime API

The Runtime API is the hot path. Every governed action passes through it.

### 2.1 Endpoints

#### `POST /v1/runtime/govern`

The canonical governed-action endpoint. Customer agent submits an action; Verixa returns allow/deny/escalate with audit reference.

**Request body:**
```yaml
agent_identity:
  spiffe_id: spiffe://customer.bank.example/agents/loan-officer-bot
  role: loan-officer
  workflow_id: wf_loan_application_v2
action:
  type: tool_call
  tool_name: transfer_funds
  arguments:
    from_account: "ACC-12345"
    to_account: "ACC-67890"
    amount: 5000
    currency: GBP
context:
  prompt_hash: sha256:abc123...
  retrieved_documents:
    - doc_id: doc_001
      hash: sha256:def456...
  model_version: qwen3-72b@2025-12-01
  reasoning_chain_summary: "Customer requested transfer to verified beneficiary..."
  workflow_state: pending_disbursement
trace_id: 01HW...  # OpenTelemetry trace ID
```

**Response (allow):**
```yaml
decision: allow
audit_id: aud_01HX...
risk_score: 0.23
risk_classification: low
policies_applied:
  - id: fs.transfer.amount_limit_v3
    result: pass
  - id: fs.transfer.beneficiary_verification_v2
    result: pass
triad_invoked: false
latency_ms: 38
```

**Response (deny):**
```yaml
decision: deny
audit_id: aud_01HY...
reason: hard_policy_breach
policy_id: fs.transfer.amount_limit_v3
policy_message: "Transfer amount £15000 exceeds role limit £10000 for loan-officer"
risk_score: 0.91
risk_classification: high
latency_ms: 42
remediation_suggestion: "Escalate to senior officer or split transfer below £10000"
```

**Response (escalate):**
```yaml
decision: escalate
audit_id: aud_01HZ...
escalation_target: human_review
escalation_id: esc_01J0...
risk_score: 0.78
risk_classification: high
triad_invoked: true
triad_consensus: 2_safe_1_unsafe
estimated_review_time_minutes: 15
status_check_url: /v1/runtime/escalation/esc_01J0...
latency_ms: 847
```

**Response codes:**
- `200 OK` — decision returned (allow / deny / escalate)
- `400 Bad Request` — schema validation failure
- `401 Unauthorized` — agent identity not recognised
- `403 Forbidden` — agent identity not permitted to use this workflow
- `429 Too Many Requests` — tenant rate limit exceeded
- `500 Internal Server Error` — Verixa error; action treated as deny by default per policy

#### `GET /v1/runtime/escalation/{escalation_id}`

Polls the status of an escalated action. Customer agent uses this to wait for human review outcome.

**Response:**
```yaml
escalation_id: esc_01J0...
status: pending  # pending | approved | denied | timeout
reviewer:
  identity: john.doe@customer.bank
  role: senior-loan-officer
  decision_at: null  # filled on completion
decision: null  # filled on completion: allow | deny
notes: null
```

#### `POST /v1/runtime/openai/v1/chat/completions`

OpenAI-compatible proxy endpoint. Customer agent points its OpenAI SDK at Verixa instead of OpenAI; Verixa governs every completion request and routes to the customer's actual model provider.

Request and response schemas mirror the OpenAI Chat Completions API. Verixa adds:
- `verixa_audit_id` in response headers
- `verixa_decision` in response headers (allow / deny / escalate)
- 403 status with Verixa policy message on deny

This is the lowest-friction integration path for customers already using OpenAI-compatible SDKs.

#### `POST /v1/runtime/sdk/wrap`

SDK-mode endpoint. Customer's tool-call decorator wraps tool invocations and submits them to Verixa via this endpoint. Functionally identical to `/v1/runtime/govern` but with SDK-specific request envelope.

### 2.2 Runtime API rate limits and SLAs

| Tier | Governed actions/sec | Triad invocations/sec | p99 latency target |
|---|---|---|---|
| Pilot | 10 | 1 | 100 ms (low-risk) / 1500 ms (triad) |
| Enterprise | 100 | 10 | 50 ms / 1000 ms |
| Sovereign Managed | 200 | 20 | 50 ms / 1000 ms |
| Hosted SaaS | 50 | 5 | 80 ms / 1200 ms |

Customer can purchase additional capacity via Pricing add-ons.

---

## 3. Control Plane API

Admin and query operations. Lower throughput, broader surface.

### 3.1 Endpoint groups

#### `/v1/control/agents` — Agent registry

- `POST /v1/control/agents` — register an agent identity
- `GET /v1/control/agents` — list agents (paginated)
- `GET /v1/control/agents/{agent_id}` — get agent detail
- `PATCH /v1/control/agents/{agent_id}` — update agent metadata
- `DELETE /v1/control/agents/{agent_id}` — deregister agent (soft delete; audit trail preserved)

#### `/v1/control/workflows` — Workflow registry

- `POST /v1/control/workflows` — register a workflow
- `GET /v1/control/workflows` — list workflows
- `GET /v1/control/workflows/{workflow_id}` — get workflow detail
- `PATCH /v1/control/workflows/{workflow_id}` — update workflow risk classification, applicable policies, escalation targets
- `GET /v1/control/workflows/{workflow_id}/risk-history` — workflow risk telemetry over time

#### `/v1/control/policies` — Rego policy management

- `POST /v1/control/policies` — author a new Rego policy
- `GET /v1/control/policies` — list policies (filter by compliance pack, applicable workflow)
- `GET /v1/control/policies/{policy_id}` — get policy detail
- `PUT /v1/control/policies/{policy_id}` — update policy (creates new version; old versions retained)
- `POST /v1/control/policies/{policy_id}/test` — run policy against test fixtures; returns pass/fail with traces

#### `/v1/control/triage` — Triage and Triad configuration

- `GET /v1/control/triage/thresholds` — get current risk thresholds for triad invocation
- `PUT /v1/control/triage/thresholds` — update thresholds (admin-only)
- `GET /v1/control/triage/disagreement-policy` — get current disagreement-handling policy
- `PUT /v1/control/triage/disagreement-policy` — update disagreement policy

#### `/v1/control/audit` — Audit Ledger queries

- `GET /v1/control/audit/{audit_id}` — get a single audit entry with full context
- `POST /v1/control/audit/query` — query audit entries by workflow / agent / time-range / decision / risk
- `GET /v1/control/audit/{audit_id}/verify` — verify hash-chain integrity for a specific entry
- `GET /v1/control/audit/integrity-check` — full ledger integrity check (long-running; returns job ID)

#### `/v1/control/replay` — Replay Vault queries

- `POST /v1/control/replay/{audit_id}` — request replay of a specific decision
- `GET /v1/control/replay/jobs/{job_id}` — get replay job status (replay is async for snapshot reconstruction)
- `GET /v1/control/replay/jobs/{job_id}/result` — get replay result bundle
- `POST /v1/control/replay/{audit_id}/what-if` — run historical decision against current policy + model + triad (clearly distinct from primary replay)

#### `/v1/control/dossier` — Compliance Dossier Generator

- `POST /v1/control/dossier/generate` — generate Annex IV-aligned dossier for a workflow / time range / regulator
- `GET /v1/control/dossier/{dossier_id}` — get dossier metadata
- `GET /v1/control/dossier/{dossier_id}/download` — download PDF + JSON + signed hash chain

#### `/v1/control/trust-graph` — Trust Graph queries (Phase 4+)

- `GET /v1/control/trust-graph/agents/{agent_id}/drift` — agent drift history
- `GET /v1/control/trust-graph/workflows/{workflow_id}/failure-memory` — workflow failure pattern
- `GET /v1/control/trust-graph/reviewers/{reviewer_id}/effectiveness` — reviewer effectiveness metrics
- `GET /v1/control/trust-graph/suppliers/{supplier_id}/trust-score` — supplier trust score
- `POST /v1/control/trust-graph/query` — arbitrary graph query (Cypher-equivalent for Apache AGE; native graph DB syntax otherwise)

#### `/v1/control/escalations` — Human review console backend

- `GET /v1/control/escalations` — list escalations (filter by status, reviewer, workflow)
- `GET /v1/control/escalations/{escalation_id}` — get escalation detail with full context
- `POST /v1/control/escalations/{escalation_id}/decide` — reviewer submits decision (approve / deny + notes)

#### `/v1/control/health` — Operational health

- `GET /v1/control/health` — overall health check (200 OK if healthy)
- `GET /v1/control/health/components` — per-component health (Runtime, Reviewers, Storage, etc.)
- `GET /v1/control/metrics` — Prometheus-format metrics

### 3.2 Control Plane API authentication

- Human users: OIDC via customer IAM, MFA required for production
- Service-to-service: mTLS with SPIFFE certificates
- Long-lived API keys: discouraged; supported only for legacy integrations, rotated quarterly

---

## 4. Webhook / Event API

Verixa emits events outbound to customer systems on significant occurrences.

### 4.1 Event types

| Event | When emitted | Default destination |
|---|---|---|
| `audit.entry.created` | Every governed action | Customer SIEM |
| `decision.deny` | Every deny decision | Customer SIEM + ITSM |
| `decision.escalated` | Every escalation | Customer ITSM (review queue) |
| `policy.violation` | Hard policy breach | Customer SIEM + on-call |
| `triad.disagreement` | Reviewers disagreed in high-risk action | Customer SIEM + on-call |
| `replay.requested` | Replay job initiated | Customer audit log |
| `dossier.generated` | Compliance dossier produced | Customer compliance team mailbox |
| `drift.detected` | Model Drift Monitor flagged a model (Phase 3+) | Customer ML team + ML-Ops |
| `incident.opened` | Verixa-detected incident | Customer ITSM (incident queue) |
| `trust_graph.anomaly` | Trust Graph anomaly detection (Phase 4+) | Customer security team |

### 4.2 Webhook security

- All webhooks signed with Verixa-tenant-specific Ed25519 signing key
- Customer destination endpoint verifies signature before processing
- Webhook delivery includes nonce + timestamp; replays detectable
- Failed deliveries retried with exponential backoff; dead letter queue after 24 hours
- Customer can subscribe / unsubscribe per event type via Control Plane API

### 4.3 Webhook payload example (`audit.entry.created`)

```yaml
event_id: evt_01J1...
event_type: audit.entry.created
event_time: 2026-05-10T03:42:11.123Z
tenant_id: customer-bank-example
audit_entry:
  audit_id: aud_01HX...
  workflow_id: wf_loan_application_v2
  agent_id: spiffe://customer.bank.example/agents/loan-officer-bot
  action_type: tool_call
  tool_name: transfer_funds
  decision: allow
  risk_score: 0.23
  risk_classification: low
  triad_invoked: false
  policies_applied:
    - id: fs.transfer.amount_limit_v3
      result: pass
  hash_chain_position: 1234567
  hash_chain_prev: sha256:...
  hash_chain_self: sha256:...
  signature: ed25519:...
signature_meta:
  signing_key_id: key_2026Q2_tenant_customer-bank
  signature_alg: ed25519
  webhook_signature: ed25519:...
```

---

## 5. OpenAPI 3.1 stub

Skeleton OpenAPI 3.1 specification for the Runtime API:

```yaml
openapi: 3.1.0
info:
  title: Verixa Runtime API
  version: 1.0.0
  description: Runtime governance for AI-driven actions
  contact:
    name: Verixa
    url: https://verixa.example/
servers:
  - url: https://{customer-tenant}.verixa.example/v1
    variables:
      customer-tenant:
        default: tenant-id
security:
  - mTLS: []
  - bearerAuth: []
paths:
  /runtime/govern:
    post:
      operationId: governAction
      summary: Submit a governed action for runtime decision
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GovernActionRequest'
      responses:
        '200':
          description: Decision returned
          content:
            application/json:
              schema:
                oneOf:
                  - $ref: '#/components/schemas/AllowResponse'
                  - $ref: '#/components/schemas/DenyResponse'
                  - $ref: '#/components/schemas/EscalateResponse'
        '400': { $ref: '#/components/responses/BadRequest' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/Forbidden' }
        '429': { $ref: '#/components/responses/RateLimit' }
  /runtime/escalation/{escalation_id}:
    get:
      operationId: getEscalation
      parameters:
        - name: escalation_id
          in: path
          required: true
          schema: { type: string }
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/EscalationStatus' }
components:
  securitySchemes:
    mTLS:
      type: mutualTLS
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    GovernActionRequest:
      type: object
      required: [agent_identity, action, context]
      properties:
        agent_identity:
          $ref: '#/components/schemas/AgentIdentity'
        action:
          $ref: '#/components/schemas/Action'
        context:
          $ref: '#/components/schemas/ActionContext'
        trace_id: { type: string }
    AgentIdentity:
      type: object
      required: [spiffe_id, role, workflow_id]
      properties:
        spiffe_id: { type: string, format: spiffe }
        role: { type: string }
        workflow_id: { type: string }
    Action:
      type: object
      required: [type]
      properties:
        type: { type: string, enum: [tool_call, completion, decision, action] }
        tool_name: { type: string }
        arguments: { type: object, additionalProperties: true }
    ActionContext:
      type: object
      properties:
        prompt_hash: { type: string }
        retrieved_documents:
          type: array
          items: { $ref: '#/components/schemas/Document' }
        model_version: { type: string }
        reasoning_chain_summary: { type: string }
        workflow_state: { type: string }
    Document:
      type: object
      required: [doc_id, hash]
      properties:
        doc_id: { type: string }
        hash: { type: string }
    AllowResponse:
      type: object
      required: [decision, audit_id, risk_score, risk_classification]
      properties:
        decision: { type: string, enum: [allow] }
        audit_id: { type: string }
        risk_score: { type: number, format: float }
        risk_classification: { type: string, enum: [low, medium, high] }
        policies_applied:
          type: array
          items: { $ref: '#/components/schemas/PolicyResult' }
        triad_invoked: { type: boolean }
        latency_ms: { type: integer }
    DenyResponse:
      type: object
      required: [decision, audit_id, reason]
      properties:
        decision: { type: string, enum: [deny] }
        audit_id: { type: string }
        reason: { type: string }
        policy_id: { type: string }
        policy_message: { type: string }
        risk_score: { type: number, format: float }
        risk_classification: { type: string }
        remediation_suggestion: { type: string }
    EscalateResponse:
      type: object
      required: [decision, audit_id, escalation_id]
      properties:
        decision: { type: string, enum: [escalate] }
        audit_id: { type: string }
        escalation_id: { type: string }
        escalation_target: { type: string }
        risk_score: { type: number, format: float }
        risk_classification: { type: string }
        triad_invoked: { type: boolean }
        triad_consensus: { type: string }
        estimated_review_time_minutes: { type: integer }
        status_check_url: { type: string }
    PolicyResult:
      type: object
      required: [id, result]
      properties:
        id: { type: string }
        result: { type: string, enum: [pass, fail, abstain] }
        message: { type: string }
    EscalationStatus:
      type: object
      properties:
        escalation_id: { type: string }
        status: { type: string, enum: [pending, approved, denied, timeout] }
        reviewer:
          type: object
          properties:
            identity: { type: string }
            role: { type: string }
            decision_at: { type: string, format: date-time, nullable: true }
        decision: { type: string, nullable: true, enum: [allow, deny, null] }
        notes: { type: string, nullable: true }
  responses:
    BadRequest:
      description: Malformed request
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorResponse' }
    Unauthorized:
      description: Authentication failure
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorResponse' }
    Forbidden:
      description: Authorisation failure
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorResponse' }
    RateLimit:
      description: Tenant rate limit exceeded
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorResponse' }
```

The Control Plane API and Webhook Event API have analogous OpenAPI specs maintained alongside the Runtime API spec.

---

## 6. SDK and client libraries

Verixa publishes client SDKs for major customer integration languages:

- **Python:** `verixa-python` — async-first, includes decorator-based wrap (`@verixa.govern`)
- **TypeScript / Node:** `verixa-ts` — for Next.js / agent-platform integrations
- **Java:** `verixa-java` — for enterprise Java agents (Phase 2)
- **Go:** `verixa-go` — for sidecar integration scenarios (Phase 2)
- **OpenAPI-generated:** auto-generated clients for any language from the OpenAPI specs

SDKs are MIT-licensed and published to PyPI / npm / Maven Central.

---

## 7. API versioning and deprecation

- **Major versions** (`/v1`, `/v2`): breaking changes; old major versions supported for 24 months after a new major version GA
- **Minor versions:** backward-compatible additions; signaled via response headers (`X-Verixa-API-Version: 1.3.2`)
- **Deprecation:** 6-month deprecation notice for any endpoint; deprecation warning in response headers; deprecated endpoints removed at next major version

---

*This API Specification is the canonical interface contract for Verixa. The full OpenAPI YAML files are version-controlled in the implementation repository. The Data Model document specifies the persistent schemas behind these APIs. The Threat Model covers the attack surface of these APIs in detail.*
