# Verixa — Testing & Quality Assurance

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline test strategy + Phase 0 hackathon scope · Audience: QA lead, engineering lead, customer's audit/test reviewer, Big 4 advisor

---

## 1. Purpose

This document specifies how Verixa is tested. It covers:

- The **test strategy** — what we test, why, how rigorously
- The **test plan** — what test types exist and how they map to risk
- The **test cases** — the canonical test catalogue at three abstraction levels
- The **automation strategy** — how tests run, where, and on what cadence
- The **use-case flows and scenarios** — end-to-end customer journeys exercised by tests
- The **release-gate criteria** — what must pass before code moves to the next environment
- The **regulator-and-audit-grade evidence** that test execution itself produces

This document is paired with the SRE & Operations document (which covers production operations) and the Build Plan (which sequences phase deliveries).

---

## 2. Test strategy

### 2.1 Why testing matters more for Verixa than for typical SaaS

Verixa sits inline in the customer's regulated AI execution path. A test gap is not just a feature defect — it is a governance failure. Three properties make Verixa testing non-negotiable:

1. **Hot-path correctness is operational risk.** A regression in the Runtime Gateway, Tool Call Firewall, or Decision Router can allow ungoverned actions through. The Audit Ledger may still record what happened, but the action will already have hit the customer's downstream systems.
2. **Audit Ledger integrity is regulator risk.** A regression in the hash-chain or signing path that goes undetected for hours could break the chain of evidence the customer is contractually committed to producing. There is no way to "fix the past"; the audit ledger must be right the first time.
3. **Determinism in replay is contractual.** Customers and regulators rely on Verixa replay to reconstruct past decisions. A regression that breaks snapshot-bundle reconstruction destroys evidence that customers have already shipped to regulators.

These properties drive the test strategy: the closer to the hot path or the audit ledger, the more rigorous the testing.

### 2.2 Test pyramid

Verixa follows a classical test pyramid with explicit ratios:

```text
                  /\
                 /  \
                /E2E \    ~5% of test count, ~30% of confidence
               /------\
              /        \
             /Integration\ ~20% of test count, ~30% of confidence
            /------------\
           /              \
          /  Component      \  ~25% of test count, ~20% of confidence
         /------------------\
        /                    \
       /       Unit            \  ~50% of test count, ~20% of confidence
      /------------------------\
```

Plus three orthogonal layers that don't fit the pyramid neatly:

- **Property-based tests** — for hash-chain, OPA-policy, and triad-commit-reveal correctness
- **Contract tests** — for the Runtime API, Control Plane API, Webhook Event API
- **Chaos/resilience tests** — for HA + DR scenarios

### 2.3 Test ownership

| Test type | Owner | Review |
|---|---|---|
| Unit | Engineer who writes the code | Code reviewer |
| Component | Engineer who writes the code | Code reviewer + tech lead |
| Integration | Engineer + QA pair | Tech lead |
| Contract | API owner | Architect |
| E2E | QA + Engineering | QA lead + Engineering lead |
| Property-based | Architect-defined; engineer-implemented | Chief Architect on hot-path tests |
| Chaos | SRE + Engineering | Chief Architect + SRE Lead |
| Performance | Engineering + SRE | Chief Architect on hot-path latency targets |
| Security | Security + Engineering | Security Architect |
| Compliance | Compliance + Engineering | Compliance Officer |
| Acceptance (customer-facing) | Customer Success + Engineering | Customer's test team |

---

## 3. Test plan

### 3.1 Test types and risk-mapping

| Test type | What it covers | Risk it mitigates | Tooling |
|---|---|---|---|
| Unit | Pure functions, single classes | Logic bugs in isolation | pytest, Vitest |
| Component | Single module with mocked collaborators | Module behaviour | pytest, Vitest |
| Integration | Multiple modules together with real DB / Redis / OPA | Integration bugs | pytest with testcontainers |
| Contract | API request/response shapes | API drift between client and server | Schemathesis, Pact |
| Property-based | Invariants over generated inputs | Edge cases not enumerated by hand | Hypothesis (Python), fast-check (TS) |
| End-to-end | Full system from customer agent → Verixa → tool execution | System-level correctness | Playwright |
| Chaos | Component-failure resilience | HA / DR claims | Chaos Toolkit, custom |
| Performance | Latency, throughput, capacity | SLO claims | k6, Locust |
| Load | Sustained-load behaviour | Capacity planning | k6, Locust |
| Security | OWASP Top 10 web + LLM Top 10 + STRIDE coverage | Security regressions | OWASP ZAP, Burp, custom Rego policies |
| Compliance | Regulatory-mapping evidence | Regulatory regressions | Custom evidence-pack verifier |
| Acceptance | Customer-defined success criteria | Customer-specific risks | Customer-driven test suites |

### 3.2 Test environments

| Environment | Purpose | Refreshed | Data |
|---|---|---|---|
| Local dev | Engineer-driven inner loop | On demand | Synthetic |
| CI | Per-PR validation | Per pipeline run | Synthetic |
| Integration | Multi-component testing | Daily | Synthetic |
| Pre-production / staging | Full release rehearsal | Per release candidate | Synthetic + anonymised production-shape data |
| Production-like (sovereign mirror) | Customer-environment-mirroring (Tier 3 / 4 customers) | Per release | Customer-anonymised |
| Production | The live system | Continuous | Real customer data |

Customer pilot environments are treated as production-grade for test rigour: no untested release reaches a customer pilot.

---

## 4. Test cases — canonical catalogue

This catalogue is illustrative not exhaustive; the live test catalogue is in the implementation repo at `tests/`. The catalogue here defines the mandatory test classes that every Phase 1 release must include.

### 4.1 Runtime Gateway (`apps/runtime/gateway`)

**Unit tests:**
- `test_request_envelope_construction` — wrap incoming action correctly with workflow context, agent identity, model identity, timestamp
- `test_authentication_spiffe_id_validated` — reject requests without valid SPIFFE ID
- `test_authentication_api_key_validated` — reject requests without valid API key (legacy mode)
- `test_schema_validation_rejects_malformed_action` — Pydantic v2 validation
- `test_idempotency_key_replay_returns_cached_response` — within 24-hour window
- `test_trace_id_propagated_to_audit_emit` — OpenTelemetry trace continuity

**Component tests:**
- `test_gateway_with_mock_firewall_passes_allowed_action` — happy path
- `test_gateway_with_mock_firewall_blocks_disallowed_action` — deny path
- `test_gateway_with_mock_decision_router_returns_correct_response_shape` — for allow / deny / escalate

**Integration tests:**
- `test_gateway_to_firewall_to_policy_to_risk_to_router_full_chain` — entire hot path on real OPA + real Postgres
- `test_gateway_audit_emit_records_correct_chain_position` — audit ledger integrity
- `test_gateway_idempotency_with_real_redis` — idempotency with real Redis backend

### 4.2 Tool Call Firewall (`apps/runtime/firewall`)

**Unit tests:**
- `test_tool_in_allowlist_passes` — allow-list matching
- `test_tool_not_in_allowlist_blocked` — default-deny
- `test_argument_within_bounds_passes` — bound enforcement (e.g. amount ≤ £10,000)
- `test_argument_exceeds_bound_blocked` — out-of-bound
- `test_per_role_allowlist_enforced` — role-based allow-lists
- `test_argument_schema_validation` — type and structure of tool arguments

**Property-based tests:**
- `property_argument_bound_enforcement_for_all_numeric_types` — Hypothesis-generated numeric inputs
- `property_allowlist_decisions_are_deterministic` — same input always same output

### 4.3 Policy Engine — OPA + Rego (`apps/runtime/policy`)

**Unit tests (per-policy, against test fixtures):**
- For every Rego policy, a fixture file with `pass`, `fail`, and `abstain` cases
- Auto-generated test scaffolding so adding a policy auto-creates the fixture skeleton
- Policy versioning: old version's fixtures still pass

**Component tests:**
- `test_opa_evaluator_loads_signed_policy_bundle` — signature verification on policy load
- `test_opa_evaluator_rejects_unsigned_bundle` — fail-closed
- `test_opa_evaluator_caches_decision_for_5_seconds` — Redis cache hit
- `test_opa_evaluator_invalidates_cache_on_policy_update` — cache coherence

**Integration tests:**
- `test_compliance_pack_financial_services_full_coverage` — every policy in the FS pack runs against fixtures
- `test_policy_evaluation_emits_audit_record_with_policy_id_and_version` — audit ledger records which policy version applied

### 4.4 Risk Engine (`apps/runtime/risk`)

**Unit tests:**
- `test_risk_score_for_low_risk_workflow_low_action_low_agent_returns_low` — composite score
- `test_risk_score_for_high_risk_workflow_returns_high` — workflow-driven
- `test_risk_classification_threshold_low_medium_high` — classification edge values

**Component tests:**
- `test_risk_engine_with_trust_graph_drift_signal_increases_score` — Phase 4+ Trust Graph integration

### 4.5 Decision Router (`apps/runtime/router`)

**Unit tests:**
- `test_low_risk_action_routed_allow` — happy path
- `test_high_risk_action_routed_to_triad` — triad invocation
- `test_hard_policy_breach_routed_deny_regardless_of_triad` — block-priority
- `test_policy_flag_routes_to_human_review` — escalation path
- `test_disagreement_policy_consensus_2_of_3_allow` — triad consensus rules
- `test_disagreement_policy_consensus_2_of_3_deny` — triad consensus rules
- `test_disagreement_policy_no_consensus_escalates` — fall-through to human review

### 4.6 Triad Review Engine (`apps/runtime/triad`) — high-stakes module

**Unit tests:**
- `test_commit_phase_three_hashes_recorded_before_any_reveal` — protocol invariant
- `test_reveal_phase_consensus_computed_correctly_2_safe_1_unsafe` — known consensus case
- `test_reveal_phase_consensus_computed_correctly_3_safe_0_unsafe` — known consensus case
- `test_reveal_phase_disagreement_handled_per_policy` — disagreement routing
- `test_reviewer_timeout_treated_as_no_verdict_per_policy` — DoS resilience

**Property-based tests:**
- `property_commit_hash_cannot_be_forged_post_reveal` — Hypothesis-generated reviewer outputs; post-reveal hash always matches commit
- `property_reveal_after_commit_required` — protocol invariant

**Integration tests:**
- `test_triad_with_real_vllm_reviewer_models_on_mi300x` — full triad against actual reviewer model deployments
- `test_triad_with_one_reviewer_unavailable_falls_back_per_policy` — HA scenario

### 4.7 Evidence Validator (`apps/runtime/evidence`)

**Unit tests:**
- `test_claim_grounded_in_retrieved_document_passes` — evidence-grounding
- `test_claim_not_in_retrieved_documents_flagged` — ungrounded claim
- `test_claim_contradicted_by_retrieved_document_flagged_high_risk` — contradiction case

### 4.8 Audit Ledger (`apps/runtime/audit`) — highest-stakes module

**Unit tests:**
- `test_hash_chain_self_correctly_computed_from_inputs` — algorithm correctness
- `test_signature_verifies_with_correct_public_key` — Ed25519 round-trip
- `test_signature_fails_with_wrong_public_key` — negative case
- `test_genesis_hash_computed_correctly_for_tenant` — tenant-bound genesis
- `test_sequence_number_monotonically_increasing` — invariant
- `test_audit_emit_record_includes_signing_key_id` — key rotation traceability

**Property-based tests:**
- `property_hash_chain_unbroken_for_any_sequence_of_entries` — Hypothesis-generated entries; chain always validates
- `property_tampering_with_any_entry_breaks_chain_integrity` — tamper-evidence
- `property_truncating_then_re_signing_detected_by_signing_key_history` — anti-rollback

**Integration tests:**
- `test_audit_ledger_full_chain_walk_from_genesis_to_latest` — end-to-end integrity
- `test_signing_key_rotation_quarterly_preserves_old_entry_verifiability` — key rotation continuity
- `test_audit_emit_under_postgres_failover_preserves_no_data_loss` — RPO 0

**Chaos tests:**
- `test_audit_emit_under_redis_outage` — graceful degradation
- `test_audit_emit_under_postgres_primary_outage_with_replica_promotion` — failover

### 4.9 Replay Vault (`apps/runtime/replay`)

**Unit tests:**
- `test_snapshot_bundle_manifest_includes_all_required_sections` — bundle layout
- `test_snapshot_bundle_encryption_round_trip_with_correct_key` — AES-256-GCM
- `test_snapshot_bundle_decryption_fails_with_wrong_key` — negative case
- `test_object_store_key_includes_content_hash` — content-addressable

**Integration tests:**
- `test_replay_reconstruction_returns_full_decision_context` — replay correctness
- `test_replay_for_decision_deleted_from_hot_tier_falls_back_to_warm` — tiering
- `test_what_if_replay_runs_historical_decision_against_current_policy` — what-if replay distinct from primary
- `test_data_subject_redaction_destroys_per_subject_key_irrecoverably` — GDPR Article 17 erasure mechanics

### 4.10 Compliance Dossier Generator (`apps/control/dossier`)

**Unit tests:**
- `test_per_decision_pack_structure_matches_canonical_layout` — pack layout invariant
- `test_per_workflow_pack_includes_all_audit_entries_in_scope` — completeness
- `test_annex_iv_dossier_includes_8_required_sections` — Annex IV section coverage
- `test_pack_manifest_signature_verifies` — Ed25519 round-trip on pack signature
- `test_pack_hash_chain_proof_validates_full_chain_walk` — proof correctness

**Integration tests:**
- `test_per_workflow_pack_generation_against_3_month_synthetic_audit_data` — large-scope generation
- `test_annex_iv_dossier_pdf_renders_correctly` — PDF rendering output
- `test_pack_offline_verification_via_verifier_shell_script` — independent verification

**Compliance tests:**
- `test_dossier_includes_evidence_for_eu_ai_act_article_9` — risk management evidence
- `test_dossier_includes_evidence_for_eu_ai_act_article_14` — human oversight evidence
- `test_dossier_includes_evidence_for_eu_ai_act_article_72` — post-market monitoring evidence

### 4.11 Control Plane API (`apps/control-plane/api`)

**Unit tests per endpoint:**
- Schema validation, RBAC enforcement, error responses, idempotency

**Contract tests:**
- OpenAPI 3.1 spec generated from FastAPI; Schemathesis runs spec-driven tests on every endpoint

**Integration tests:**
- `test_workflow_registration_appears_in_audit_ledger` — admin operations are auditable
- `test_policy_authoring_requires_signed_policy_bundle_before_activation` — signing requirement
- `test_replay_request_creates_audit_entry_for_replay_event` — replay-as-audit-event

### 4.12 Control Plane UI (`apps/control-plane/ui`)

**Unit tests (Vitest):**
- Component-level tests for every key component (workflow list, audit query, replay viewer, dossier generator, escalation queue)

**E2E tests (Playwright):**
- Full UI flows; see §5 use-case flows below

### 4.13 SDKs (`packages/verixa-python`, `packages/verixa-ts`)

**Unit + integration tests:**
- SDK wraps governed-action correctly with envelope
- Decorator mode (`@verixa.govern`) works
- OpenAI-compatible proxy mode works
- SDK handles allow / deny / escalate response correctly
- SDK retries on 429 with exponential backoff

---

## 5. Use-case flows and end-to-end scenarios

The canonical use-case flows are the customer journeys Verixa is built to support. Each is exercised by an end-to-end automated test plus a manual exploratory test in pre-production.

### 5.1 UC-01: Register a workflow and govern its first action

**Persona:** Customer's Head of AI Governance + AI engineer.

**Steps:**
1. Head of AI Governance logs into Control Plane via OIDC (customer IdP)
2. Registers a new workflow (e.g. "loan_application_v2") with risk classification "high" and FS compliance pack
3. Engineer registers an agent identity bound to the workflow
4. Engineer registers a tool ("transfer_funds") with argument bounds
5. Engineer's AI agent submits a governed action via SDK
6. Verixa Runtime Gateway receives action, validates schema, validates SPIFFE identity
7. Tool Call Firewall validates against allow-list and bounds
8. Policy Engine evaluates FS compliance pack policies
9. Risk Engine scores the action
10. Decision Router routes (allow / deny / escalate) per risk + policy
11. Audit Ledger writes hash-chained signed entry
12. Replay Vault snapshots the decision context
13. Engineer's agent receives decision response

**E2E test:** `test_e2e_uc01_register_workflow_govern_first_action`

**Acceptance criteria:**
- Workflow visible in Control Plane within 1 second of registration
- Action decision returned within 50 ms (p99) for low-risk path
- Audit entry visible in audit query within 1 second
- Replay reconstruction works on the resulting decision

### 5.2 UC-02: High-risk action invokes Triad Review

**Persona:** Customer's AI agent + reviewer models on customer MI300X.

**Steps:**
1. Agent submits action with high-risk classification (e.g. transfer > £10,000)
2. Decision Router invokes Triad Review Engine
3. Reviewer A receives review package, computes verdict, commits hash to Audit Ledger
4. Reviewer B receives same package independently, commits hash
5. Reviewer C receives same package independently, commits hash
6. After all 3 commits recorded, reveal phase begins
7. Each reviewer reveals verdict + nonce; consensus computed
8. If 3-of-3 safe: allow. If 2-of-3 safe: per policy. If split: escalate to human review

**E2E test:** `test_e2e_uc02_high_risk_invokes_triad`

**Acceptance criteria:**
- Triad latency p99 ≤ 1000 ms with mixed reviewer model sizes
- Hash commits all written to Audit Ledger before any verdict revealed (cryptographic non-collusion check)
- Consensus computation correct against fixture cases

### 5.3 UC-03: Reviewer disagreement escalates to human review

**Persona:** Customer's senior compliance officer.

**Steps:**
1. UC-02 happens with reviewer disagreement (e.g. 2 safe, 1 unsafe)
2. Decision Router routes to human review queue
3. Senior compliance officer logs in, sees pending escalation in queue
4. Reviews full decision context: action, agent, workflow, policy evaluation, risk score, triad verdicts + reasoning
5. Decides approve / deny + notes
6. Human Review record written with reviewer identity + IAM authentication trace
7. Agent receives delayed response with human-review outcome

**E2E test:** `test_e2e_uc03_triad_disagreement_human_review`

**Acceptance criteria:**
- Escalation appears in queue within 1 second of triad disagreement
- Reviewer can see all triad verdicts + reasoning
- Decision propagates back to waiting agent within 1 second of reviewer submit
- Audit entry includes both triad record and human review record

### 5.4 UC-04: Regulator visit — generate Annex IV-aligned dossier

**Persona:** Customer's Compliance Officer responding to regulator inquiry.

**Steps:**
1. Customer's Compliance Officer logs into Control Plane
2. Selects workflow + time range (e.g. Jan 1 – Mar 31)
3. Selects "Annex IV-aligned dossier" pack type and target regulator
4. Verixa generates dossier asynchronously (Celery job)
5. Job pulls all in-scope audit entries, verifies hash-chain integrity, pulls policy versions, pulls replay snapshots, renders PDF, signs manifest
6. Compliance Officer downloads dossier (PDF + JSON + verifier.sh)
7. Optionally runs `verifier.sh` offline to confirm pack integrity
8. Delivers dossier to regulator

**E2E test:** `test_e2e_uc04_regulator_dossier_generation_and_offline_verification`

**Acceptance criteria:**
- Annex IV dossier for 3-month range generated within 4 hours (p99)
- All 8 Annex IV sections populated with primary-evidence backing
- Offline verifier confirms hash-chain integrity and signature validity
- Pack manifest signature verifies against published public key

### 5.5 UC-05: Auditor replays a specific past decision

**Persona:** Big 4 auditor reviewing customer's AI governance.

**Steps:**
1. Auditor (with auditor RBAC role) logs into Control Plane
2. Queries Audit Ledger for a specific past decision (by audit_id or by workflow + timestamp)
3. Selects "Replay" on that decision
4. Verixa retrieves snapshot bundle from Replay Vault (hot / warm / cold tier as appropriate)
5. Verixa decrypts bundle, reconstructs decision context: model version, prompt, retrieved documents, tool inputs, reviewer verdicts, final decision
6. Auditor inspects all reconstructed context
7. Optionally runs "what-if replay" — same inputs against current policy + model + triad — to compare past vs current

**E2E test:** `test_e2e_uc05_auditor_replay_past_decision`

**Acceptance criteria:**
- Hot-tier replay returns within 30 seconds (p99)
- Warm-tier replay returns within 60 seconds (p99)
- Reconstructed context matches original decision record exactly
- What-if replay clearly distinguishes from primary replay in UI and audit log

### 5.6 UC-06: Policy update lifecycle

**Persona:** Customer's policy author (compliance team).

**Steps:**
1. Policy author opens Policy Authoring UI
2. Edits an existing Rego policy or creates new one
3. Adds test fixtures with `pass` / `fail` / `abstain` cases
4. Runs policy test harness; all fixtures must pass
5. Submits for review by senior policy author
6. Senior policy author approves; signed policy bundle compiled
7. Bundle deployed to Policy Engine; old version retained for replay
8. Audit Ledger records policy update with author + timestamp + diff

**E2E test:** `test_e2e_uc06_policy_authoring_test_review_deploy_audit`

**Acceptance criteria:**
- Policy test harness blocks deployment if fixtures fail
- Policy bundle signing works end-to-end
- Old policy version still loadable for historical replay
- Audit Ledger captures policy change as auditable event

### 5.7 UC-07: Customer SIEM receives webhook event

**Persona:** Customer's Security Operations Centre.

**Steps:**
1. Verixa decision occurs (any decision class)
2. Webhook event API emits signed event to customer SIEM endpoint
3. Customer SIEM verifies Ed25519 signature using published public key
4. Customer SIEM ingests event into security data lake
5. Customer security team can correlate Verixa governance events with other security telemetry

**E2E test:** `test_e2e_uc07_webhook_signed_delivery_with_signature_verification`

**Acceptance criteria:**
- Webhook delivered within 5 seconds (p99 of first attempt)
- Signature verifies against published public key
- Failed delivery retries with exponential backoff and dead-letters at 24 hours
- Customer can subscribe / unsubscribe per event type via Control Plane API

### 5.8 UC-08: Data subject erasure request

**Persona:** Customer's Data Protection Officer responding to GDPR Article 17 request.

**Steps:**
1. DPO opens Control Plane Data Subject Rights interface
2. Submits subject identifier + request type (access / erasure)
3. For erasure: Verixa walks audit ledger for entries containing subject identifier in retrieved-document references or tool arguments stored in Replay Vault snapshots
4. Verixa cryptographic-erases per-subject encryption key from Vault
5. Audit ledger entry remains (regulatory retention) but subject-identifiable content in snapshots is irrecoverable
6. DPO receives erasure receipt with redaction proof

**E2E test:** `test_e2e_uc08_data_subject_erasure_with_audit_preservation`

**Acceptance criteria:**
- Subject identifier locatable across audit ledger + replay vault
- Per-subject encryption key destruction is irrecoverable
- Audit ledger entries remain valid post-redaction
- Erasure receipt includes cryptographic redaction proof

### 5.9 UC-09: Sovereign deployment with no outbound egress for reviewer models

**Persona:** Defence sector deployment engineer.

**Steps:**
1. Customer-controlled MI300X cluster in sovereign environment
2. Verixa deployed via Helm; reviewer model network has no outbound internet egress allowed at firewall level
3. Triad Review invocations execute against sovereign reviewer models
4. No prompts, no governance data, no operational telemetry leaves customer trust boundary
5. Verifiable via network egress audit

**E2E test:** `test_e2e_uc09_sovereign_deployment_zero_egress_verification`

**Acceptance criteria:**
- Reviewer model deployment has network policy denying all egress except to Verixa Runtime Container internal endpoint
- Synthetic egress probe (e.g. attempted DNS resolution to external host) blocked
- Customer security team can verify zero-egress via firewall logs
- Functional triad still works correctly under zero-egress configuration

### 5.10 UC-10: Hot path under sustained load (capacity validation)

**Persona:** Customer's capacity-planning team.

**Steps:**
1. Synthetic load generator submits governed actions at sustained rate (e.g. 100 actions/sec for Tier 2 customer)
2. Verixa Runtime Gateway, Tool Call Firewall, Policy Engine, Risk Engine, Decision Router, Audit Emit all handle the load
3. Audit Ledger growth tracked; replicas keep up; no data loss
4. p50, p95, p99 latency measured against SLO targets
5. Test extends to triad invocation under load

**Performance test:** `perf_test_uc10_sustained_load_at_target_capacity`

**Acceptance criteria:**
- Sustained 100 actions/sec for Tier 2 target with ≤ 50 ms p99 latency on low-risk path
- Sustained 10 triad invocations/sec for Tier 2 target with ≤ 1000 ms p99 latency on triad path
- Zero audit emit data loss
- Memory and connection-pool stable over 1-hour sustained run

---

## 6. Automation strategy

### 6.1 CI / CD pipeline

```text
[Engineer commits + pushes]
        |
        v
[GitHub Actions]
        |
        v
[Lint + format check] ─── ruff, black, mypy, eslint, prettier
        |
        v
[Unit tests] ────────────── pytest, Vitest
        |
        v
[Component tests] ──────── pytest, Vitest
        |
        v
[Build container images]
        |
        v
[Sign images + SBOM] ───── Cosign + Syft
        |
        v
[Integration tests in CI] testcontainers Postgres + Redis + OPA
        |
        v
[Contract tests] ───────── Schemathesis
        |
        v
[Deploy to integration env]
        |
        v
[E2E tests] ────────────── Playwright
        |
        v
[Performance smoke test] ─ k6 baseline
        |
        v
[Security scan] ────────── ZAP, Trivy on built images
        |
        v
[Compliance test] ──────── evidence-pack verifier on synthetic data
        |
        v
[Approve for staging deploy]
        |
        v
[Deploy to staging]
        |
        v
[Full E2E suite + manual exploratory]
        |
        v
[Approve for prod release]
        |
        v
[Phased rollout to Tier 4 → Tier 3 → Tier 2 → Tier 1]
```

### 6.2 Test execution cadence

| Test type | Cadence | Environment |
|---|---|---|
| Unit | Per commit | CI |
| Component | Per commit | CI |
| Integration | Per PR | CI |
| Contract | Per PR | CI |
| E2E | Per PR + nightly | CI + integration env |
| Property-based | Per PR for hot-path modules; nightly full | CI |
| Performance smoke | Per PR | CI |
| Performance full | Nightly + per release candidate | Pre-prod |
| Load | Per release candidate | Pre-prod |
| Chaos | Per release candidate + monthly continuous | Pre-prod |
| Security scan | Per PR + weekly full scan | CI + Pre-prod |
| Compliance | Per PR + per release candidate | CI + Pre-prod |
| Penetration test | Annual third-party | Pre-prod (mirror of prod) |

### 6.3 Test data management

- **Synthetic data** is the default for CI / integration. Generated from fixture libraries; covers low-risk and high-risk scenarios across sectors.
- **Anonymised production-shape data** for staging only, for customers who consent. PII redacted; structural shape preserved.
- **Real production data** never used outside production. No "production data in dev" scenarios are permitted.
- **Customer pilot data** stays in customer environment for Tier 1 / 2 deployments; Verixa engineers troubleshoot in customer environment under customer access controls.

### 6.4 Coverage targets

- **Backend unit + component:** 90% line coverage on hot-path modules; 80% on cold-path
- **Frontend unit + component:** 80% line coverage on key flows
- **E2E flows:** every named UC-XX scenario has at least one passing automated test
- **Contract:** 100% of API endpoints covered by Schemathesis-generated tests
- **Property-based:** every cryptographic invariant has at least one property test

Coverage is a floor, not a ceiling; quality of tests matters more than line count. Code review explicitly rejects "coverage padding" PRs that increase line coverage without testing meaningful behaviour.

### 6.5 Mutation testing (Phase 2+)

Mutation testing on critical modules (Audit Ledger, Triad Review, Policy Engine) using `mutmut` (Python) and `Stryker` (TS). Target mutation score: 70%+ on critical modules. Mutation tests run nightly, not per-PR (too slow for inner loop).

---

## 7. Performance and capacity testing

### 7.1 Performance SLO validation

For every release candidate, the performance test suite validates the SLOs defined in the SRE & Operations document:

| SLO | Test | Pass criteria |
|---|---|---|
| p99 ≤ 50 ms low-risk path | `perf_low_risk_p99` | p99 < 50 ms over 10-min sustained run |
| p99 ≤ 1000 ms triad path | `perf_triad_p99` | p99 < 1000 ms over 10-min sustained run |
| 100 actions/sec sustained | `perf_throughput_tier2` | No queue depth growth, no error rate increase |
| 10 triad/sec sustained | `perf_triad_throughput_tier2` | No reviewer model timeout increase |

### 7.2 Capacity envelope testing

Per-quarter capacity envelope test:
- Ramp load until any SLO breach
- Capture the breaking point (actions/sec, triads/sec, replay queries/sec)
- Compare to advertised tier capacity
- Adjust capacity messaging if the envelope has narrowed (hardware change, code change)

### 7.3 Latency budget profiling

The hot path has a documented latency budget (System Architecture Document §6). Per-release performance profiling validates the budget is still met:

- Steps 1–5 (gateway + firewall) ≤ 5 ms ✓
- Step 6 (policy evaluation) ≤ 10 ms ✓
- Steps 7–10 (risk + routing) ≤ 5 ms ✓
- Steps 11–15 (triad, when triggered) ≤ 800 ms ✓
- Steps 16–19 (audit emit + snapshot) ≤ 20 ms async ✓

Regression in any sub-budget triggers an engineering investigation before release approval.

---

## 8. Chaos and resilience testing

### 8.1 Chaos scenarios

Per-release-candidate chaos test scenarios (executed in pre-production, not production):

1. **Postgres primary kill** — verify replica promotion + RTO 30 seconds + RPO 0 audit
2. **Object store unavailable** — verify graceful degradation + alerting
3. **Vault unavailable** — verify queued signing operations + alerting
4. **Single Triad reviewer model down** — verify fall-back to two-of-three per policy
5. **Two Triad reviewer models down** — verify fall-back to single-reviewer with auto-escalate per policy
6. **Redis outage** — verify rate limit + idempotency degraded but still safe
7. **Customer IAM (OIDC) down** — verify Control Plane degraded mode + cached tokens
8. **Webhook destination down** — verify backoff + dead-letter at 24 hours
9. **OPA policy bundle invalid** — verify fall-back to last-known-good + alerting
10. **MI300X capacity saturation** — verify Triad scheduling backoff + Risk Engine throttling

Each scenario has a chaos test in `tests/chaos/` and a runbook in the SRE & Operations document.

### 8.2 Annual full DR drill

Tier 3 / 4 deployments: annual full DR drill exercising the documented DR runbook end-to-end. Customer can attend or observe; results published in customer's annual operational summary.

---

## 9. Security testing

### 9.1 OWASP Top 10 web (Control Plane UI + APIs)

OWASP ZAP automated scan per release candidate; manual penetration test annually. Coverage:
- Broken access control — RBAC enforcement test cases
- Cryptographic failures — TLS 1.3 enforcement, weak cipher rejection
- Injection — parameterised query test, schema validation negative tests
- Insecure design — covered by Threat Model + design review
- Security misconfiguration — CIS-benchmark scan
- Vulnerable components — Trivy scan
- Authentication failures — IdP integration tests
- Data integrity — image signature verification
- Logging failures — internal admin audit-trail tests
- SSRF — egress allow-list tests

### 9.2 OWASP Top 10 for LLMs

Per Threat Model §5, every OWASP LLM risk has at least one explicit test:
- LLM01 prompt injection → Phase 2 input controls + action-side test cases
- LLM02 insecure output handling → Tool Call Firewall test cases
- LLM07 insecure plugin design → Tool Call Firewall test cases
- LLM08 excessive agency → role allow-list tests + Approval Matrix tests (Phase 2+)

### 9.3 STRIDE tests

Each STRIDE-identified threat in the Threat Model has at least one test:
- Spoofing → SPIFFE identity validation tests
- Tampering → hash-chain integrity tests
- Repudiation → signed audit ledger tests
- Information disclosure → encryption + RBAC tests
- Denial of service → rate-limit + chaos tests
- Elevation of privilege → RBAC tests + policy tests

### 9.4 Cryptographic correctness

Cryptographic primitives (SHA-256, Ed25519, AES-256-GCM) are not implemented by Verixa; we use vetted libraries (`cryptography` for Python, well-known native bindings). Tests validate Verixa's *use* of these primitives:
- Round-trip tests for sign/verify, encrypt/decrypt
- Negative tests for tampered inputs
- Property-based tests for invariants (commit-reveal protocol, hash chain)

---

## 10. Compliance testing

### 10.1 Regulatory mapping evidence tests

Per Regulatory Mapping Matrix §4–6, every VRX control has at least one test that produces evidence the control is operative:

- VRX-RUN-01 (inline interception) — `test_runtime_intercepts_every_governed_action`
- VRX-VER-01 (multi-model triad) — `test_triad_invokes_three_independent_reviewers`
- VRX-EVD-01 (hash-chained audit ledger) — `test_audit_ledger_hash_chain_integrity_full_walk`
- VRX-EVD-02 (snapshot replay) — `test_replay_reconstruction_returns_full_decision_context`
- VRX-EVD-03 (Annex IV dossier) — `test_annex_iv_dossier_includes_8_required_sections`
- ... (every VRX control has at least one paired test)

The Compliance Dossier Generator emits dossier output; Verixa's compliance test suite runs the Compliance Dossier Generator against synthetic audit data and verifies output covers every Annex IV section and every applicable regulatory mapping.

### 10.2 Sector compliance pack tests

For every sector compliance pack (financial services, healthcare, public sector, defence, energy):
- Every Rego policy in the pack has fixture-based tests
- Sector-specific use-case scenarios run against the pack
- Big 4 advisor review (Phase 2+) annually
- Sector regulator engagement when invited by customer (Phase 1+)

---

## 11. Acceptance testing for customer pilots

Each pilot deployment has a customer-defined acceptance test plan negotiated at SOW signing. Typical acceptance criteria:

- Customer's named workflow successfully governed for [N] days
- [N] decisions made, including [N] triads, including [N] human review escalations
- Compliance Dossier generated against [N]-month time range
- Replay of at least [N] specific past decisions demonstrated
- Customer's compliance / audit / Big 4 advisor review of dossier output
- Joint test plan execution with customer's test team
- Customer's CISO sign-off on security posture

Acceptance tests are customer-specific; Verixa's role is to support customer's test team, provide test data, and demonstrate against customer's chosen scenarios.

---

## 12. Phase 0 hackathon-specific test scope

For the AT-Hack0017 submission specifically:

**Mandatory at submission:**
- Unit + component tests for Runtime Gateway, Tool Call Firewall, Policy Engine, Risk Engine, Decision Router, Triad Review Engine, Audit Ledger, Replay Vault, Evidence Validator, Compliance Dossier Generator
- Integration tests for the full hot path
- E2E tests for at least UC-01 (register and govern), UC-02 (triad invoked), UC-04 (dossier generation), UC-05 (replay)
- Coverage targets: pytest @ 100% on hot-path; Vitest @ 100% on key UI flows
- Playwright E2E on the canonical demo scenario

**Out-of-scope at hackathon submission (deferred to Phase 1+):**
- Full chaos test suite — only basic graceful-degradation tests included
- Performance SLO validation at Tier 2 capacity — only smoke tests
- Mutation testing — Phase 2+
- Penetration test — Phase 1+
- Sector compliance pack tests beyond financial services sample — Phase 2+

The hackathon test scope is calibrated to demonstrate the architecture works end-to-end against the demo scenario, with clear forward-roadmap for production-grade test coverage.

---

## 13. Test maintenance and retirement

- **Test retirement:** when a feature is removed or replaced, related tests retired; replacement tests written first (test-first refactor)
- **Flaky test policy:** flaky tests fixed within 5 business days or quarantined with a tracking ticket; flaky-test backlog reviewed weekly
- **Test debt:** measured per release; backlog tracked in engineering; reduction targets published quarterly

---

## 14. Test artefacts shared with customers

- **Test summary report** per release candidate — high-level pass/fail counts per test type
- **Compliance test evidence** per regulatory mapping — produced by Compliance Dossier Generator
- **Performance regression report** per release — SLO compliance summary
- **Penetration test executive summary** — annually
- **Customer pilot acceptance test results** — per pilot, customer-specific

---

*This Testing & Quality Assurance document is the canonical test reference for Verixa. The Build Plan defines what's testable in each phase. The SRE & Operations document defines what's measured in production. The Threat Model and Regulatory Mapping Matrix define the risk surface that tests cover. Updates require QA Lead + Engineering Lead approval and quarterly review.*
