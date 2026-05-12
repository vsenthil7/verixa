# Phase roadmap (CP-86 onwards) — what comes next

CP-grain planning ledger for everything still to ship. Aligns with the capability-grain phase structure defined in `docs/15_build_plan/BUILD_PLAN.md`. Status is one of:

- **🔜 next** — should land in the next session(s); blocker-free
- **⏳ queued** — sequenced but waiting on a prior CP or on external setup
- **🔒 phase-gated** — committed to a phase but not estimated/sized yet; sized at the phase gate

This file is a planning artefact. Do NOT append committed CPs here; append them to `CP_PROGRESS_LEDGER.md`.

---

## Phase 1 finish — v0.2.0 SDK release + persistence + auth + mTLS (CP-86 → CP-~140)

Phase 1 in `BUILD_PLAN.md` is the "Runtime Governance Core" — first commercial pilot deployment with regulated UK/EU enterprise customer. The Phase-0 prototype (CP-01..CP-44) gave us the runtime + control plane. The Phase-1+ block (CP-45..CP-85) gave us SDK publish-readiness, typed-response surface, and the v0.2.0 release artefacts. **The Phase-1 finish work below is the last gap between "v0.2.0 SDK released" and "ready for the first £150k pilot SOW".**

### CP-86 → CP-89 — Close out v0.2.0 release

| CP | Status | Subject | Estimated complexity |
|---|---|---|---|
| CP-86 | 🔜 next | Python + TS README updates: fix `owner_tenant_id` → `sector + risk_threshold_escalate` in Quickstart code samples; fix all 4 v0.1.0 wire-format bugs in README examples; add "Typed responses" section documenting `return_typed=True` / `returnTyped: true` opt-in pattern; refresh Roadmap section to reflect actual v0.2.0 delivery (typed envelopes already shipped, NOT "will ship in v0.4.0"); strike stale "v0.2.0 will add ..." promises that didn't ship (sync wrapper, webhook receiver helper, retry-with-backoff). 1 session. | Medium — careful per-language coordination so both READMEs stay symmetric. |
| CP-87 | ⏳ queued | Publisher one-time setup. PyPI: account at https://pypi.org/manage/account/publishing/ → add pending publisher (project `verixa`, owner `vsenthil7`, repo `verixa`, workflow `release.yml`, environment `release-pypi`). npm: generate granular token (publish:packages scope on `@verixa/*`, 90-day expiry) → add as `NPM_TOKEN` repo secret → also as `release-npm` environment secret → verify `@verixa` scope provenance-eligible. No code change; account-level operator work. Out-of-band. | Low — UI work only, ~1 hour total. |
| CP-88 | ⏳ queued | `workflow_dispatch` dry-run via Actions UI per `docs/15_build_plan/SDK_RELEASE_RUNBOOK.md` §3. Run with `dry_run=true` (default); confirm `verify` + `build-python` + `build-npm` all green; download both artefacts; verify-install in fresh venv + fresh npm dir; assert versions match `0.2.0`. Gates: CP-87 complete. | Low — protocol is documented; just executing the runbook. |
| CP-89 | ⏳ queued | `git push origin v0.2.0` — triggers the real release.yml run. Monitor all 6 jobs; approve the `release-pypi` + `release-npm` environment gates; verify PyPI page exists, npm page exists with provenance attestation, GitHub Release page has both artefacts attached. Gates: CP-87 + CP-88 both green. | Low — single command + 20 min of monitoring. |

### CP-90 → CP-~110 — Persistence swap (InMemory* → Postgres* / MinIO*)

Per ADR-0001 + ADR-0006. The Phase-0 prototype uses `InMemoryAuditLedger`, `InMemoryDossierStore`, `InMemoryWorkflowRegistry`, etc. For Phase 1 pilot deployment these must swap to real persistence so deployments survive restart + scale beyond a single process. The DB schemas (CP-03.x) already exist; the swap is at the storage-class boundary.

| CP (planned) | Status | Subject | Notes |
|---|---|---|---|
| CP-90 | ⏳ queued | `PostgresWorkflowRegistry` (replaces `InMemoryWorkflowRegistry`) — SQLAlchemy async + asyncpg; tests against testcontainers Postgres | Schema already at CP-03.2 |
| CP-91 | ⏳ queued | `PostgresAgentRegistry` (replaces `InMemoryAgentRegistry`) | Schema already at CP-03.2 |
| CP-92 | ⏳ queued | `PostgresToolRegistry` (replaces `InMemoryToolRegistry`) | Schema already at CP-03.2 |
| CP-93 | ⏳ queued | `PostgresAuditLedger` (replaces `InMemoryAuditLedger`) — append-only with hash-chain continuation across processes | Schema already at CP-03.4 |
| CP-94 | ⏳ queued | `PostgresDossierStore` (replaces `InMemoryDossierStore`) — PDF blob references + JSON manifest | Schema already at CP-03.7 |
| CP-95 | ⏳ queued | `MinioBundleStore` wiring — already exists at CP-12.6; wire as default replay-vault store in production config | Code complete; config-only |
| CP-96 | ⏳ queued | `RedisPolicyCache` wiring — already exists at CP-8.5; wire as default OPA decision cache in production config | Code complete; config-only |
| CP-97 | ⏳ queued | `PostgresWebhookSubscriptionStore` (replaces `InMemoryWebhookDispatcher` storage half) | Need new migration |
| CP-98 | ⏳ queued | `PostgresPolicyStore` for Rego bundle versions (replaces filesystem-only loader) | Schema already at CP-03.3 |
| CP-99 | ⏳ queued | `migrations/` end-to-end smoke test: Alembic upgrade head → fresh DB → seed → verify all queries work | Closes the InMemory→Postgres swap |
| CP-100 | ⏳ queued | Production-grade Postgres HA topology docs (primary + 2 read replicas, Patroni failover) | Per BUILD_PLAN §3.2 |

### CP-~111 → CP-~125 — Real auth: SPIFFE/SPIRE + Vault PKI + cert-manager

Per ADR-0007 + ADR-0008. CP-53 shipped the mTLS Protocol scaffold; the real implementation is here.

| CP (planned) | Status | Subject |
|---|---|---|
| CP-111 | ⏳ queued | Vault PKI engine setup: root CA + intermediate CA for `verixa-internal-mesh`; cert-manager Vault issuer |
| CP-112 | ⏳ queued | SPIFFE/SPIRE deployment: spire-server + spire-agent per node + workload attestor for k8s pod-identity |
| CP-113 | ⏳ queued | Verixa workload SVID registration: control-plane + runtime + reviewers each get a SPIFFE ID |
| CP-114 | ⏳ queued | mTLS server side: Verixa control plane requires client cert with SPIFFE ID in `verixa-internal-mesh` trust domain |
| CP-115 | ⏳ queued | mTLS client side: Verixa SDK mTLS authentication helper (Python + TS); replaces / augments Bearer API key |
| CP-116 | ⏳ queued | Customer IAM integration: OIDC SAML for Control Plane UI; admin/policy-author/reviewer/auditor/viewer role mapping |
| CP-117 | ⏳ queued | Vault customer-managed key hierarchy: per-tenant signing key + encryption key delegated to customer Vault |
| CP-118 | ⏳ queued | Token rotation runbook: SPIFFE SVID 1h TTL → automatic renewal; Vault PKI cert 24h TTL → cert-manager renewal |
| CP-119 | ⏳ queued | Auth negative tests: expired SVID rejected; unauthorised trust-domain rejected; OIDC token replay rejected |
| CP-120 | ⏳ queued | Threat-model update: ADR-0007/0008 promoted to Accepted from Proposed; cross-reference to STRIDE entries |

### CP-~126 → CP-~140 — Multi-tenancy UI + Approval Matrix + pilot deployment hardening

Per ADR-0009 + BUILD_PLAN §3.2 ("Customer-deployment-grade hardening").

| CP (planned) | Status | Subject |
|---|---|---|
| CP-126 | ⏳ queued | Multi-tenant UI: tenant selector in Control Plane UI header; URL scoping `/t/{tenant_slug}/...`; RBAC role binding shown in UI |
| CP-127 | ⏳ queued | UC-11 Approval Matrix backend: `authority_role` + `approval_threshold` per workflow; OPA-enforced gate on R3-escalate |
| CP-128 | ⏳ queued | UC-11 Approval Matrix UI: approval inbox; decision capture with MFA prompt; escalation tree visualisation |
| CP-129 | ⏳ queued | SLA tracking on approval queue: time-to-first-look + time-to-decide; breach alerts to ops |
| CP-130 | ⏳ queued | Operational runbook: incident response playbook; on-call rotation; runbook-driven SRE handoff |
| CP-131 | ⏳ queued | Customer pilot SOW template: success criteria; joint-test-plan schema; regulator-engagement-ready output spec |
| CP-132 | ⏳ queued | Customer policy authoring tooling: Rego linter; test-fixture generator from past audit entries; CI for customer policy repo |
| CP-133 | ⏳ queued | Customer SIEM webhook: payload schema for Splunk + Sentinel + Chronicle; replay-on-failure semantics |
| CP-134 | ⏳ queued | Customer ITSM webhook: ServiceNow + Jira incident creation on policy breach |
| CP-135 | ⏳ queued | Pilot success metrics dashboard: KPIs from `docs/18_sre_and_operations/KPI_DASHBOARD.md` wired to live data |

---

## Phase 2 — Enterprise Control Plane (CP-~141 → CP-~200)

Per `BUILD_PLAN.md` §4. Q1 2027. Window: post-first-pilot success. Headline: human-in-the-loop, sector compliance packs, full Annex IV-aligned dossier, input-side controls.

| CP block | Status | Capability cluster | Notes |
|---|---|---|---|
| CP-141 → CP-160 | 🔒 phase-gated | Human Review Console at full scope: reviewer queue UI with workflow context; evidence panel; decision capture; SLA tracking; reviewer effectiveness scoring (foundation for Phase 4 Trust Graph) | Builds on CP-126..CP-129 UI work |
| CP-161 → CP-170 | 🔒 phase-gated | Approval Matrix Engine: authority-based role bindings; escalation tree; time-bound approvals; MFA at decision time | CP-127..CP-128 was Phase-1 minimum; Phase-2 is full scope |
| CP-171 → CP-180 | 🔒 phase-gated | Full Compliance Dossier Generator: all 4 pack types (per-decision, per-workflow, Annex IV, Article 72) with full PDF rendering via WeasyPrint + LaTeX fallback | CP-13.1 / CP-13.2 was per-decision only |
| CP-181 → CP-185 | 🔒 phase-gated | Contradiction Detector: cross-step reasoning contradiction detection; embeddings-based; per-workflow tuned thresholds | Net-new capability |
| CP-186 → CP-190 | 🔒 phase-gated | Hallucination Risk Engine: unsupported-claim + unverified-assertion scoring; integrates with Evidence Validator from CP-11.1 | Net-new capability |
| CP-191 → CP-195 | 🔒 phase-gated | Sector compliance packs: financial services (FCA + PRA + EBA), healthcare (MHRA + FDA SaMD), public sector (UK + EU member state) — Rego bundles + dossier templates | CP-8.2 was financial-services starter |
| CP-196 → CP-198 | 🔒 phase-gated | Input-side controls: PII redaction (Microsoft Presidio); prompt-injection detection; source-document trust scoring | Net-new capability surface |
| CP-199 → CP-200 | 🔒 phase-gated | RBAC at full scope: admin / policy author / reviewer / auditor / viewer roles with OPA-enforced gates | CP-126 was tenant selector only |

**Phase 2 gate criteria** (per BUILD_PLAN §4.2):
- 5+ Phase 1 pilots converted to Tier 2 Enterprise contracts
- 1+ regulator engagement on Phase 2-customer Annex IV dossier
- SOC 2 Type I attestation initiated
- Sector compliance packs validated by Big 4 advisor for ≥2 sectors

---

## Phase 3 — Sovereign Runtime (CP-~201 → CP-~260)

Per `BUILD_PLAN.md` §5. Q2–Q3 2027. Production-grade sovereign deployment for regulated sectors; ISO 27001 / ISO 42001 certifications; drift monitoring.

| CP block | Status | Capability cluster | Notes |
|---|---|---|---|
| CP-201 → CP-215 | 🔒 phase-gated | Sovereign Runtime hardening: air-gap-capable deployment patterns; hardware HSM integration option (Thales / AWS CloudHSM); customer-controlled-key-only mode | Builds on CP-117 customer-managed Vault |
| CP-216 → CP-225 | 🔒 phase-gated | Model Drift Monitor: primary-model drift detection; reviewer-model drift detection; statistical-baseline-against-history; alerts wired to SIEM | Net-new module `verixa_runtime.drift` |
| CP-226 → CP-235 | 🔒 phase-gated | Sidecar / service-mesh integration mode: Istio + Cilium integration patterns; customer-mesh-agnostic interface | Builds on CP-53 mTLS scaffold |
| CP-236 → CP-245 | 🔒 phase-gated | SOC 2 Type II attestation work: 12-month observation period; evidence collection automation; auditor engagement | Long-running compliance work |
| CP-246 → CP-250 | 🔒 phase-gated | ISO 27001 certification: ISMS scope definition; risk treatment plan; Stage 1 + Stage 2 audits | Long-running compliance work |
| CP-251 → CP-255 | 🔒 phase-gated | ISO/IEC 42001 certification (AI Management Systems) — Verixa dogfoods its own product to maintain conformance | First-mover in this certification |
| CP-256 → CP-260 | 🔒 phase-gated | Tier 3 Sovereign Managed deployments: first customers on Verixa-operated dedicated tenancy on AMD Developer Cloud | Per BUILD_PLAN §5.2 success criteria |

**Phase 3 gate criteria** (per BUILD_PLAN §5.2):
- 3+ Tier 3 Sovereign Managed deployments in production
- ISO 42001 certification achieved (first AI-governance vendor)
- 1+ defence-sector or public-sector reference customer

---

## Phase 4 — Trust Graph + Human Operations (CP-~261 → CP-~320)

Per `BUILD_PLAN.md` §6. Q4 2027. Long-term operational intelligence platform; Trust Graph as moat; managed human review operations.

| CP block | Status | Capability cluster | Notes |
|---|---|---|---|
| CP-261 → CP-280 | 🔒 phase-gated | Trust Graph at full scope: Apache AGE on Postgres for default tier; Neo4j integration for very large customers | Builds on CP-03.x Postgres schemas |
| CP-281 → CP-295 | 🔒 phase-gated | Trust Graph queries: agent drift history; workflow failure memory; reviewer effectiveness; supplier trust scoring; escalation heatmaps; AI incident lineage; cross-agent behavioural patterns | Each query is its own CP |
| CP-296 → CP-305 | 🔒 phase-gated | WET Ops: managed human review operations service tier; Verixa-operated reviewer pool with regulated-sector training | Business + product work |
| CP-306 → CP-310 | 🔒 phase-gated | Workflow anomaly detection: Trust Graph-driven flagging of unusual workflow patterns | Builds on CP-261..CP-280 |
| CP-311 → CP-315 | 🔒 phase-gated | Reviewer effectiveness dashboards: Control Plane UI surface for reviewer quality | Builds on Phase 2 Review Console |
| CP-316 → CP-320 | 🔒 phase-gated | Trust Graph in Compliance Dossier: operational intelligence summaries in Annex IV / Article 72 packs | Builds on Phase 2 dossier work |

**Phase 4 gate criteria** (per BUILD_PLAN §6.2):
- 80%+ of Tier 2/3 customers using Trust Graph queries in regulator engagement
- WET Ops adopted by ≥2 customers as managed-review tier
- Trust Graph informs ≥1 customer's procurement on a third-party AI supplier

---

## Phase 5 — Third-party AI Governance (CP-~321 → CP-~400)

Per `BUILD_PLAN.md` §7. Q1–Q2 2028. Verixa governs third-party AI products (Copilot, Salesforce, ServiceNow, etc.) without internal SaaS introspection; Bench, Hallmark, Forge, Replica modules ship.

| CP block | Status | Capability cluster | Notes |
|---|---|---|---|
| CP-321 → CP-340 | 🔒 phase-gated | **Bench** — model + workflow evaluation harness for use-case-specific selection | Net-new product module |
| CP-341 → CP-360 | 🔒 phase-gated | **Hallmark** — model + data provenance attestation with cryptographic verification | Net-new product module |
| CP-361 → CP-380 | 🔒 phase-gated | **Forge** — policy authoring studio with natural-language to Rego compilation | Net-new product module |
| CP-381 → CP-395 | 🔒 phase-gated | **Replica** — standalone simulation and replay sandbox for pre-deployment stress testing | Net-new product module |
| CP-396 → CP-400 | 🔒 phase-gated | Third-party AI wrappers: Copilot, Salesforce Einstein, ServiceNow Now Assist — governed via API wrappers + event gateways + browser-side policy enforcement | Customer-specific work; sequenced per customer |

**Phase 5 gate criteria** (per BUILD_PLAN §7.2):
- 3+ customers deploying Verixa as governance for third-party AI products
- Hallmark provenance attestation referenced in ≥1 customer's regulator engagement
- Forge reduces customer policy-authoring time by 50%+ for new workflows

---

## Phase 6 — Federated Trust Mesh (CP-~401 → CP-~450)

Per `BUILD_PLAN.md` §8. Q3–Q4 2028. Cross-organisation attestation, supplier evidence sharing, regulator evidence exchange.

| CP block | Status | Capability cluster | Notes |
|---|---|---|---|
| CP-401 → CP-420 | 🔒 phase-gated | **Mesh** — federated trust network for cross-company attestations | Builds on CP-53 mTLS + CP-112 SPIFFE |
| CP-421 → CP-435 | 🔒 phase-gated | Cross-org attestation protocol: SPIFFE federation extension; cross-tenancy zero-trust trust establishment | Net-new protocol work |
| CP-436 → CP-445 | 🔒 phase-gated | Supplier evidence sharing: opt-in supplier-to-customer evidence pack delivery via Mesh | Builds on Phase 5 Hallmark |
| CP-446 → CP-450 | 🔒 phase-gated | Regulator evidence exchange: regulator-to-customer evidence query via Mesh (where regulator participates) | Requires regulator pilot |

**Phase 6 gate criteria** (per BUILD_PLAN §8.2):
- 5+ customers participating in trust mesh
- 1+ regulator pilot using mesh for supervised AI evidence exchange
- Trust mesh becomes a competitive advantage in participating customers' own markets

---

## Cross-cutting concerns (carried across all phases)

Per `BUILD_PLAN.md` §9. These are not assigned CP numbers — they're enforced as policy.

### Engineering practice
- pytest 100% backend coverage on hot path; vitest 100% frontend on key flows; Playwright E2E on canonical scenarios
- Every PR reviewed by ≥1 engineer + ≥1 architect on hot-path changes
- Every public API change accompanied by OpenAPI spec update + CHANGELOG entry
- Threat modelling at every phase gate; dependency scanning weekly; CVE patching SLA 7d crit / 30d high / 90d med

### Customer success
- 1 Customer Success engineer + 1 Compliance specialist + 1 Architect per pilot
- Annual review for every Tier 2+ customer (usage, incidents, expansion, roadmap alignment)
- Reference programme: first cohort in each sector → reference-discount in exchange for case study + reference call

### Standards-body + ecosystem engagement
- AAGATE alignment maintained; contribute where possible
- CSA AICM extension layer maintained; contribute mappings to CSA
- NIST AI RMF crosswalk maintained; participate in NIST GenAI Profile evolution
- ISO 42001 certification maintained (Phase 3+); participate in ISO/IEC SC 42 evolution
- OWASP AIVSS / Top 10 LLM: maintain cross-reference; contribute customer-anonymised attack-pattern data

### Hiring and team scale
- Phase 0 (hackathon): founding team
- Phase 1 (first pilots): 8–12 eng + 2 compliance + 2 customer success
- Phase 2 (enterprise control plane): 20–30 eng + 5 compliance + 5 CS + 3 sales + 2 marketing
- Phase 3 (sovereign runtime): 40–50 across product/eng/CS/compliance/sales/marketing/ops/security
- Phase 4–6 (platform expansion): 80–150+ depending on customer growth

---

## Open architectural decisions (deferred to phase gates)

Per `BUILD_PLAN.md` §11:

| Phase | Decision | Decision date |
|---|---|---|
| Phase 2 | Approval Matrix Engine data model (NIST RBAC vs XACML hierarchical role) | Phase-2 gate |
| Phase 4 | Trust Graph storage choice for very large customers (Apache AGE vs Neo4j vs TigerGraph) | Phase-4 gate |
| Phase 5 | Hallmark provenance protocol (in-tree vs adopt emerging open standard) | Phase-5 gate |
| Phase 6 | Federated mesh protocol (SPIFFE federation extension vs custom vs adopt emerging trust-mesh standard) | Phase-6 gate |

Each deferred decision has a designated decision date at the relevant phase gate. Chief Architect maintains the deferred-decisions register.

---

## How to use this roadmap

- **At session start:** read this top-to-bottom to refresh context on what's next.
- **At session end:** if a CP from this file landed, **MOVE the row** from here to `CP_PROGRESS_LEDGER.md` with the commit hash. Don't dual-track.
- **When inserting a new CP between existing ones:** use a decimal (e.g. `CP-86.1`) to preserve the numbering of downstream CPs. Re-numbering downstream CPs is forbidden because external references would break.
- **When a `phase-gated` block needs to be expanded into individual CPs:** open a sub-document under `docs/22_session_status/` (e.g. `PHASE_2_CP_BREAKDOWN.md`) — keep this file at the planning-grain level.

---

*This file is regenerated from `BUILD_PLAN.md` + the latest committed state at session end. Last refreshed 2026-05-12 06:16 UK at CP-85.*
