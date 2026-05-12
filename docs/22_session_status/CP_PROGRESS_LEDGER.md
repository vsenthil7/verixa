# CP progress ledger — CP-01 → CP-85

Authoritative chronological ledger of every checkpoint shipped on the Verixa codebase from initial repo init through v0.2.0 SDK release. One row per CP. Status is one of:

- **✅ done** — committed, pushed, tested green at the time it landed
- **🔧 fix** — corrective patch on a prior CP
- **📝 docs** — documentation-only

For phase classification see `docs/15_build_plan/BUILD_PLAN.md`. For what comes next see `docs/22_session_status/PHASE_ROADMAP_FUTURE.md`.

---

## Phase 0 — Hackathon prototype + Phase-1-ready foundation (CP-01 → CP-44)

### Repo init

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-01 | `44097a8` | ✅ done | chore | repo init: MIT licence, README, .gitignore, 17-doc pack carried from AT-Hack0017-002 |

### CP-02.x — Monorepo + dev stack + health endpoints

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-02.1 | `03a8cd5` | ✅ done | feat | Python monorepo skeleton + `compliance_language` module (32 tests / 100% coverage on `packages/verixa-python`) |
| CP-02.1.1 | `893797f` | ✅ done | chore | Poetry 2.x compliance + lockfile (PEP 621 `[project]` table; `poetry.lock` pinned; in-project venv) — 32 tests |
| CP-02.2 | `2433af3` | ✅ done | feat | Node monorepo skeleton (pnpm + Turborepo + Vitest); `@verixa/ts` compliance-language port (32 vitest / 100% coverage) |
| CP-02.3 | `04969d8` | ✅ done | feat | Local Docker Compose dev stack (Postgres+pgvector, Redis, OPA 0.70, Vault 1.18 dev, MinIO, Prometheus 3.1) |
| CP-02.4 | `79863ea` | ✅ done | feat | `ops.ps1` dispatcher + `Makefile` (up/down/health/test/test-py/test-ts/lint/git-* subcommands) |
| CP-02.5 | `3df071f` | ✅ done | feat | FastAPI health endpoints (Runtime + Control Plane API) — `/healthz` `/readyz` `/version` `/metrics` on both apps |

### CP-03.x — Postgres schema (7 schemas across the platform)

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-03.1 | `2b71f89` | ✅ done | feat | Alembic baseline + `verixa_tenancy` schema (`tenants` table); SQLAlchemy MetaData root with naming convention |
| CP-03.2 | `f48daa9` | ✅ done | feat | `verixa_registry` schema (agents, workflows, tools, models); 4 ORM models with check constraints |
| CP-03.3 | `cdac031` | ✅ done | feat | `verixa_policy` schema (policies, policy_test_fixtures); Rego source storage + version tracking |
| CP-03.4 | `0628841` | ✅ done | feat | `verixa_audit` schema (audit_entries + signing_keys); hash-chained Ed25519-signed append-only ledger |
| CP-03.5 | `402160a` | ✅ done | feat | `verixa_replay` schema (replay_index); one row per encrypted snapshot bundle; content-addressable |
| CP-03.6 | `50a3f93` | ✅ done | feat | `verixa_review` schema (triad_reviews + human_reviews); hash-commit-and-reveal protocol storage |
| CP-03.7 | `ee6a083` | ✅ done | feat | `verixa_dossier` schema (dossiers); PDF + JSON object keys + hash_chain anchor |

### CP-04.x — Cryptographic primitives

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-04.1 | `97d8c61` | ✅ done | feat | Ed25519 sign/verify primitives (PyNaCl/libsodium); frozen `Ed25519KeyPair` (32+32 bytes) |
| CP-04.2 | `d3a0c62` | ✅ done | feat | SHA-256 hash chain (audit-ledger integrity per data-model A7 5.2); `HashChainEntry` frozen dataclass |
| CP-04.3 | `fd8ce60` | ✅ done | feat | AES-256-GCM encrypt/decrypt (Replay Vault snapshot encryption per data-model A7 §6) |
| CP-04.4 | `475d039` | ✅ done | feat | Tenant key-bootstrap utility (Phase 0 dev mode); `TenantKeyBundle` holds signing keypair + replay key |

### CP-05.x — Audit ledger + offline verifier

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-05.1 | `165d9be` | ✅ done | feat | Audit emitter (append-only hash-chained Ed25519-signed); pure-function `emit_audit_record` |
| CP-05.2 | `694bd45` | ✅ done | feat | Audit verifier full-chain walk; `verify_audit_chain(entries, tenant_id)` raises `AuditChainError` |
| CP-05.3 | `74d2476` | ✅ done | feat | Offline `audit_verify.py` CLI; reads JSON export of audit_entries + signing_keys |
| CP-05.4 | `23677b7` | ✅ done | feat | Key-rotation continuity tests — proves verifier handles signing-key rotation end-to-end |

### CP-06.x — Runtime Gateway

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-06.1 | `10f080f` | ✅ done | feat | Runtime Gateway envelopes (Pydantic v2); `GovernRequest` (agent_identity, action, …) |
| CP-06.2 | `0799076` | ✅ done | feat | `POST /v1/runtime/govern` endpoint (Phase 0 stub pipeline); FastAPI router prefix `/v1/runtime` |
| CP-06.3 | `c98baa7` | ✅ done | feat | `POST /v1/chat/completions` OpenAI-compatible proxy → vLLM-on-ROCm endpoint |
| CP-06.4 | `d5684ef` | ✅ done | feat | API-key auth + structured JSON logging middleware; `ApiKeyMiddleware` `X-Verixa-API-Key` header |
| CP-06.5 | `f04023f` | ✅ done | feat | Auditex-style config + dotenv loader; `.env.example` mirrors Auditex naming |

### CP-07.x — Tool Call Firewall

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-07.1 | `7c10ae7` | ✅ done | feat | Tool Call Firewall allow-list (pure-function evaluator); `evaluate_allowlist` → `FirewallVerdict` |
| CP-07.2 | `9dccb54` | ✅ done | feat | Tool Call Firewall argument-bounds (closes CP-7); `evaluate_argument_bounds(action, schema)` |

### CP-08.x — Policy Engine (OPA + Rego + bundle signing + Redis cache)

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-08.1 | `76280f0` | ✅ done | feat | Rego bundle structure + 2 core policies + Python loader; `core` pack manifest |
| CP-08.2 | `66abf10` | ✅ done | feat | Financial-services policy pack; `fs-v1.0.0` manifest, roots `verixa.fs.*` |
| CP-08.3 | `66917de` | ✅ done | feat | Python OPA HTTP client (async); `OpaPolicyClient.evaluate(package, input_doc)` |
| CP-08.4 | `9859268` | ✅ done | feat | Bundle signing + signed-bundle verification (Ed25519); `.signatures.json` shape per OPA spec |
| CP-08.5 | `cc57b56` | ✅ done | feat | Redis 5s decision cache (closes CP-8); `CachedPolicyClient` short-TTL cache |
| CP-08.6 | `e777161` | ✅ done | feat | Close in-memory-Redis-stub gap with bytes tolerance + live testcontainers integration |

### CP-09.x — Risk engine + decision router

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-09.1 | `ec233a5` | ✅ done | feat | Pure-function risk engine + decision router; `RouterInputs` carries `GovernRequest` + firewall verdicts |
| CP-09.2 | `089134f` | ✅ done | feat | Wire decision router into `/v1/runtime/govern` (closes CP-9); `decide_via_router` |

### CP-10.x — Triad Review Engine (commit-reveal protocol + 3 reviewers)

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-10.1 | `b3ee16a` | ✅ done | feat | Triad commit-reveal protocol primitives (pure-function module; no I/O) |
| CP-10.1 (tests) | `3292cbc` | ✅ done | feat | Triad protocol test suite (32 unit + property tests covering dataclass invariants) |
| CP-10.1 (fix) | `0caaed5` | 🔧 fix | fix | Label-swap test exercises the rejection branch correctly |
| CP-10.2 | `9e3e4fe` | ✅ done | feat | Triad reviewer client abstraction (OpenAI-compat HTTP wrapper + `MockReviewer` + `Reviewer` Protocol) |
| CP-10.2 (tests) | `244dd8c` | ✅ done | feat | Triad reviewer test suite — 31 tests across 6 layers |
| CP-10.2 (fix) | `b68d78c` | 🔧 fix | fix | Close 100% coverage gaps in `reviewer.py` (Protocol method-body coverage exclusions) |
| CP-10.2 (chore) | `c135bec` | ✅ done | chore | Silence `pytest-asyncio` warnings on sync tests; removed module-level pytestmark |
| CP-10.3 | `da39919` | ✅ done | feat | Triad orchestrator (frozen dataclass; holds the 3 reviewers + commit-reveal coordinator) |
| CP-10.3 (tests) | `755af2a` | ✅ done | feat | Triad orchestrator test suite — 17 tests across 3 layers |
| CP-10.3 (fix) | `6c4ff0f` | 🔧 fix | fix | `test_run_reviewer_a_outage_synthesises_escalate` consensus expectation corrected |
| CP-10.5 | `e4bc588` | ✅ done | feat | Wire triad orchestrator into the gateway router on R3-escalate path; `decide_via_router_with_triad` |
| CP-10.5 (tests) | `1bbdb94` | ✅ done | feat | Gateway triad-integration test suite — 8 tests via `MockReviewer` |
| CP-10.4 | `3b8d688` | ✅ done | feat | Live MI300X triad integration test (gated; closes CP-10) — `test_triad_integration.py` |

### CP-11.x — Evidence Validator

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-11.1 | `87fea0b` | ✅ done | feat | Evidence Validator pure module — `verixa_runtime.evidence.validator` |
| CP-11.1 (tests) | `118ac1a` | ✅ done | feat | Evidence Validator test suite — 18 tests across 2 layers |

### CP-12.x — Replay Vault

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-12.1 | `9242e23` | ✅ done | feat | Replay Vault bundle types + canonical serialisation; `verixa_runtime.replay.bundle` |
| CP-12.1 (tests) | `1205854` | ✅ done | feat | Replay bundle test suite — 26 tests across 3 layers |
| CP-12.2 | `f006e39` | ✅ done | feat | Replay Vault encryption + content-addressable storage key; `verixa_runtime.replay.sealer` |
| CP-12.2 (tests) | `d7e52a5` | ✅ done | feat | Sealer test suite — 11 tests covering encrypt_bundle/decrypt_bundle |
| CP-12.3 | `0434c4c` | ✅ done | feat | Replay Vault object-store interface; `BundleStore` Protocol + `InMemoryBundleStore` |
| CP-12.3 (tests) | `5397748` | ✅ done | feat | Store test suite — 11 tests covering `InMemoryBundleStore` |
| CP-12.4 | `9969ca5` | ✅ done | feat | Replay Vault snapshotter + reconstructor; `Snapshotter` + `Reconstructor` |
| CP-12.4 (tests) | `7c58e14` | ✅ done | feat | Snapshotter test suite — 10 tests end-to-end via `InMemoryBundleStore` |
| CP-12.5 | `04a7bb8` | ✅ done | feat | Gateway wiring for replay snapshot (fire-and-forget); `decide_via_router_with_replay` |
| CP-12.5 (tests) | `3d0b1f7` | ✅ done | feat | Replay-wired gateway test suite — 6 tests |
| CP-12.6 | `4d53f1b` | ✅ done | feat | MinIO-backed `BundleStore` (production-grade replay storage); `verixa_runtime.replay.minio_store` |
| CP-12.6 (tests) | `bd24bd2` | ✅ done | feat | `MinioBundleStore` test suite (fake + gated live) |

### CP-13.x — Compliance Dossier Generator

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-13.1 / 13.2 | `7ecc376` | ✅ done | feat | Compliance Dossier Generator + manifest signing; `verixa_runtime.dossier.manifest` |
| CP-13.1 / 13.2 (tests) | `ad745ab` | ✅ done | feat | Dossier manifest test suite — 18 tests covering validation + `build_manifest` |

### CP-14.x — Control Plane API

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-14.1 | `7293911` | ✅ done | feat | Control Plane API envelope models; `verixa_control_plane.envelopes` Pydantic v2 typed request/response |
| CP-14.1 (tests) | `ede64af` | ✅ done | feat | Control Plane envelope test suite — 34 tests across 6 endpoint groups |
| CP-14.2 | `0463c5f` | ✅ done | feat | Control Plane replay + dossier handlers; `verixa_control_plane.handlers` 3 async handler functions |
| CP-14.2 (tests) | `14b2e90` | ✅ done | feat | Control Plane handlers test suite — 15 tests via `InMemoryDossierStore` |
| CP-14.3 | `5312350` | ✅ done | feat | Control Plane audit-log query handler + ledger abstraction; `verixa_control_plane.audit.AuditLedger` |
| CP-14.3 (tests) | `4f8be13` | ✅ done | feat | Audit ledger + query test suite — 13 tests covering `InMemoryAuditLedger` semantics |
| CP-14.4 | `ec76f9b` | ✅ done | feat | Control Plane registry handlers; `verixa_control_plane.registry` 3 CRUD-style registries (Workflow/Agent/Tool) |
| CP-14.4 (tests) | `b8aa930` | ✅ done | feat | Registry handlers test suite — 12 tests covering workflow + agent + tool registration |
| CP-14.5 | `1896865` | ✅ done | feat | Wire Control Plane handlers into FastAPI routes; `verixa_control_plane.routes.ControlPlaneState` |
| CP-14.5 (tests) | `0c59e82` | ✅ done | feat | Control Plane FastAPI integration test suite — 15 tests via `TestClient` |
| CP-14.5 (fix) | `8bb27e2` | 🔧 fix | fix | Cover `create_app_with_state` default-state path |

### CP-15.x — Control Plane UI (Next.js 14)

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-15.1 | `a3f5fed` | ✅ done | feat | Control Plane UI API client + types + vitest config; `apps/control-plane-ui/src/lib/api-client.ts` |
| CP-15.2 | `ebc419e` | ✅ done | feat | Verixa UI design tokens + dashboard page; single source of truth `src/components/design.ts` |
| CP-15.3 | `9bfd14b` | ✅ done | feat | Control Plane UI audit log page; Server Component with `dynamic=force-dynamic` |
| CP-15.4 | `1538ab5` | ✅ done | feat | Decision detail page at `/decisions/[audit_id]`; Server Component |
| CP-15.5 | `c54601f` | ✅ done | feat | Dossier viewer page at `/dossier/[dossier_id]`; Server Component |

### CP-16, CP-17, CP-21 — Demo seed + HF Spaces + Playwright E2E

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-16 | `2fd4d02` | ✅ done | feat | Financial-services demo seed data; `verixa_control_plane.demo_seed.seed_financial_services_demo` |
| CP-16 (tests) | `dd4650a` | ✅ done | feat | Demo seed test suite — 9 tests covering end-to-end seed |
| CP-17 | `5fb31d0` | ✅ done | feat | Hugging Face Spaces deployment artefacts under `deploy/huggingface/` + production ASGI entry |
| CP-17.2 | `d02625a` | ✅ done | feat | HF Space LIVE at https://vsenthil7-verixa-control-plane.hf.space |
| CP-21 | `e350e7a` | ✅ done | feat | Playwright E2E (18 specs) + critical `asgi.py` bug fix (uvicorn-in-asyncio-loop crash) |
| CP-21.2 | `077ca59` | ✅ done | feat | GitHub Actions CI: 3 parallel jobs (python-tests + typescript + playwright); cross-platform Playwright |
| CP-21.2 (docs) | `8f0ce58` | 📝 docs | docs | Tidy stale comments in `ci.yml` Playwright job |
| CP-22 | `077ca59` | ✅ done | fix | Dashboard fetch-cache bug fix (`cache: 'no-store'` on `api-client.ts`); landed with CP-21.2 |
| CP-23 | `9426366` | 📝 docs | docs | README polish for hackathon judging (honest Phase 0 vs Phase 1 deviation table) |
| CP-24a | `c53ae31` | ✅ done | chore | Ruff auto-fix 221 of 240 issues across 87 files |
| CP-24b | `75d1e94` | ✅ done | chore | Ruff UP038 sweep — 6 isinstance tuple → PEP-604 union across 4 files |
| CP-24c | `2738825` | ✅ done | chore | Ruff `noqa` sweep — 9 false-positive lint issues annotated |
| CP-24d | `b46ad32` | ✅ done | chore | Final 4 ruff issues fixed manually |
| CP-25 | `b70325e` | 📝 docs | docs | `USE_CASES.md` with mermaid sequence diagrams + README link |
| CP-25.1 | `f001d27` | 🔧 fix | docs | `USE_CASES.md` test paths grounded in real files; 6 invented test names replaced |
| CP-26 | `cd7fe77` | ✅ done | refactor | `docs/` canonical renumbering (17 folders via two-stage `git mv`; history preserved) |
| CP-27 | `ad155fc` | 📝 docs | docs | BRD + USER_STORIES + TRACEABILITY_MATRIX + sweep 25 doc-path refs |
| CP-28 | `fdd98e7` | 📝 docs | docs | `NEGATIVE_TEST_PLAN.md` — 31% negative-test coverage measured + 10 known gaps documented |
| CP-29a | `4f8e36c` | 📝 docs | docs | 4 repo-root market-standard docs: SECURITY + CONTRIBUTING + COC + CHANGELOG |
| CP-29b | `2dbda99` | 📝 docs | docs | 5 ADRs (ADR-0001 → ADR-0005) in `docs/07_system_architecture/adr/` |
| CP-29c | `4108850` | 📝 docs | docs | API style guide + SBOM + NOTICE — closes the 8 market-standard docs set |
| CP-30 (timeout) | `f372ad2` | ✅ done | feat | Triad reviewer timeout negative tests (6 tests) |
| CP-30 (replay) | `4852f51` | ✅ done | feat | Replay-attack negative tests (9 tests covering canonical-byte divergence) |
| CP-30 (unicode RED) | `40e4a56` | ✅ done | feat | Unicode-edges negative tests (RED-GREEN pattern; surrogate rejection at pydantic boundary) |
| CP-30 (unicode FIX) | `28d106e` | 🔧 fix | fix | Unicode-edges surrogate test corrected (pydantic v2 strict-mode rejection point) |
| CP-30 (size RED) | `189ebf4` | ✅ done | feat | Size-limits negative tests (11 tests: oversized fields + risk_score range + deep nesting) |
| CP-30 (size FIX) | `004b104` | 🔧 fix | fix | Size-limits assertions corrected (reasoning_chain + spiffe_id tests flipped to rejection-expect) |
| CP-30 (path RED) | `3b884ad` | ✅ done | feat | Path-traversal negative tests (20 tests covering POSIX/Windows/URL-encoded/null-byte) |
| CP-30 (path FIX) | `fffd857` | 🔧 fix | fix | Path-traversal long-chain test corrected (moved 100-elem chain to rejection-expect parametrize) |
| CP-30.1 | `d5ca5da` | 🔧 fix | feat | `ReplayBundle` validator rejects empty `doc_id` + empty hash; closes Phase-1 gap |
| CP-30.2 | `e6f6d53` | 🔧 fix | fix | `test_size_limits.py` xfail-strict marker removed after d5ca5da; converted to pass-expect |
| CP-30.3 | `a2c4583` | 📝 docs | docs | `API_STYLE_GUIDE.md` §3.5 field caps + `ReplayBundle` non-empty invariant |
| CP-31 | `4ff0ea3` | 📝 docs | docs | 5 Phase-1/2 placeholder ADRs (ADR-0006 → ADR-0010) in Proposed status |
| CP-32 | `d3f20a4` | ✅ done | chore | pytest `norecursedirs`: exclude `_backup` + standard noise dirs from test discovery |
| CP-33 | `f2722fc` | 📝 docs | docs | DPIA template split-out from `DATA_PROTECTION_AND_PRIVACY.md` §12 |
| CP-34 | `38bacda` | 📝 docs | docs | 3 enterprise-procurement-grade docs: RISK_REGISTER + SLO_SLA + DR_PLAN |
| CP-35 | `e71623f` | 📝 docs | docs | 3 governance + ops docs: CHANGE_MANAGEMENT_PROCESS + KPI_DASHBOARD + RACI_MATRIX |
| CP-36 | `45bbf19` | ✅ done | feat | Timing-attack negative tests for Ed25519 verification (20 tests across 7 attack categories) |
| CP-37 | `557a7ad` | ✅ done | feat | Tenant-key compromise + cryptographic-erasure negative tests (13 tests across 7 attack models) |
| CP-38 | `53453dd` | ✅ done | feat | Race-condition + concurrent-write negative tests (8 tests stressing `asyncio.Lock`) |
| CP-39 | `3b9499b` | 📝 docs | docs | `NEGATIVE_TEST_PLAN.md` updated — Phase-1 negative-test push closes; 1005 defensive-tests |
| CP-40 | `9a127d3` | ✅ done | feat | `ReconstructorAuditIdMismatch` guard + 1 new neg test; closes CP-37 attack model 7 |
| CP-41 | `c9ed63e` | 📝 docs | docs | `TRACEABILITY_MATRIX.md` extended with explicit Negative Tests column |
| CP-42 | `b2724ea` | ✅ done | feat | `load-tests/` scaffold + 3 baseline volume tests; partially closes resource-exhaustion gap |
| CP-43 | `a3d7d5a` | ✅ done | feat | `tools/policy_sign.py` CLI wrapping Ed25519 OPA bundle signing |
| CP-44 | `f4f1749` | ✅ done | feat | CycloneDX 1.6 SBOM generator + Ed25519 signer (OWASP `cyclonedx-bom` wrapper) |

---

## Phase 1 — Runtime Governance Core foundations (CP-45 → CP-60)

SDK publish-readiness: control-plane integrations + first PyPI/npm-ready alphas.

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-45 | `c79da76` | ✅ done | feat | OPA bundle distribution `BundleServer` — closes CP-43 carry-forward |
| CP-46 | `4405645` | ✅ done | feat | HTTP routes for OPA bundle distribution (`/v1/control/policy/bundles`) |
| CP-47 | `98e45d4` | ✅ done | feat | Audit ledger archival + retention scaffold per ADR-0006; `audit_archive` |
| CP-48 | `f5cca73` | ✅ done | feat | Outbound webhook event API for SIEM/ITSM; `InMemoryWebhookDispatcher` |
| CP-49 | `c65eb8e` | ✅ done | feat | HTTP routes for webhook subscriptions + delivery forensics (`/v1/control/webhooks/*`) |
| CP-50 | `8a5a103` | ✅ done | feat | `verixa-python` SDK alpha for Control Plane API; `VerixaClient` async context manager |
| CP-51 | `954c2db` | ✅ done | feat | `verixa-ts` SDK alpha for Control Plane API; cross-language symmetric surface |
| CP-52 | `8d50f66` | ✅ done | feat | Timing-attack tripwire investigation harness + xfail resolution |
| CP-53 | `f67bb2c` | ✅ done | feat | mTLS internal service-mesh `Protocol` scaffold per ADR-0007 (implementation pending Vault PKI) |
| CP-54 | `2776844` | ✅ done | feat | OpenAPI schema export + drift-detection CLI + canonical `docs/openapi.json` artefact |
| CP-55 | `8268684` | ✅ done | feat | `verixa-python` SDK PyPI publish-readiness: README + CHANGELOG + `py.typed` + pinning tests |
| CP-56 | `bd01f45` | ✅ done | feat | `verixa-ts` SDK npm publish-readiness: README + CHANGELOG + expanded `package.json` + pinning tests |
| CP-57 | `ef6be5e` | ✅ done | feat | LICENSE files in both SDK package directories (PyPI + npm publish unblocker) |
| CP-58 | `b113fd6` | ✅ done | feat | Per-package `pyproject.toml` for `verixa-python` (hatchling backend) — final PyPI blocker cleared |
| CP-59 | `a39536a` | ✅ done | feat | GitHub Actions SDK release workflow ties CP-54..CP-58 — 6-job pipeline (verify, build-py, build-npm, publish-pypi, publish-npm, github-release) |
| CP-60 | `fae3e2e` | ✅ done | feat | Pre-commit hook for OpenAPI drift gate per CP-54 follow-up |

---

## Phase 1+ — Typed-response surface (CP-61 → CP-82)

Cross-language v0.4.0-promise delivery; landed in v0.2.0 lockstep.

### CP-61 → CP-64 — Python typed envelopes COMPLETE

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-61 | `87eb363` | ✅ done | feat | Python typed envelope dataclasses (Workflow×3 + Audit×2) + `InvalidEnvelopeError` |
| CP-62 | `a15a94c` | 🔧 fix + feat | feat | FIX CP-61 wire mismatch + Agent + Tool envelopes |
| CP-63 | `02dd0ad` | ✅ done | feat | Replay + Dossier×2 envelopes |
| CP-64 | `ed46628` | ✅ done | feat | Webhook×4 envelopes — Python typed-response surface **COMPLETE** |

### CP-65 → CP-68 — TypeScript typed envelopes COMPLETE

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-65 | `6c51f88` | ✅ done | feat | TS `envelopes.ts` batch 1 (Workflow×3 + Audit×2) mirrors Python CP-61 |
| CP-66 | `cfee78e` | ✅ done | feat | TS Agent + Tool parsers mirror Python CP-62 |
| CP-67 | `f315030` | ✅ done | feat | TS Replay + Dossier×2 parsers mirror Python CP-63 |
| CP-68 | `4655305` | ✅ done | feat | TS Webhook×4 parsers — TS typed-response surface **COMPLETE** |

### CP-69 → CP-82 — Opt-in `return_typed` overloads + wire-format request-side fixes

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-69 | `9bd2a71` | 🔧 fix + feat | feat | Py `WorkflowsClient`: wire-fix (drop `owner_tenant_id`; add `sector` + `risk_threshold_escalate`) + `return_typed` overload |
| CP-70 | `e2893d7` | 🔧 fix + feat | feat | TS `WorkflowsClient`: same fix + `returnTyped` overload |
| CP-71 | `c27063d` | 🔧 fix + feat | feat | Py `AgentsClient`: wire-fix (drop `name`+`model_provider`+`model_name`; add `spiffe_id`+`role`+`description`) + `return_typed` |
| CP-72 | `4c859c1` | 🔧 fix + feat | feat | TS `AgentsClient`: same fix + `returnTyped` |
| CP-73 | `6b94bf1` | 🔧 fix + feat | feat | Py `ToolsClient`: wire-fix (drop `workflow_id`+`schema`; add `description`+`is_active`+`allowed_workflow_ids`) + `return_typed` |
| CP-74 | `efc9ca6` | 🔧 fix + feat | feat | TS `ToolsClient`: same fix + `returnTyped` |
| CP-75 | `75364a1` | 🔧 fix + feat | feat | Py `DossierClient.generate`: wire-fix (drop `tenant_id`; add `action_summary`) + dual `return_typed` overloads on generate + get |
| CP-76 | `78c6141` | 🔧 fix + feat | feat | TS `DossierClient`: same fix + dual `returnTyped` overloads |
| CP-77 | `346b904` | ✅ done | feat | Py `ReplayClient.get`: `return_typed` overload (no wire-fix needed) |
| CP-78 | `a542f0e` | ✅ done | feat | TS `ReplayClient.get`: `returnTyped` overload |
| CP-79 | `763a803` | ✅ done | feat | Py `WebhooksClient`: `return_typed` overloads on subscribe + list_subscriptions + recent_deliveries (×3 methods) |
| CP-80 | `ee18415` | ✅ done | feat | TS `WebhooksClient`: `returnTyped` overloads on all 3 methods |
| CP-81 | `dc1f5c1` | ✅ done | feat | Py `AuditClient.query`: `return_typed` overload (verified `from`/`to` aliases correct; no wire-fix) |
| CP-82 | `81bbbfd` | ✅ done | feat | TS `AuditClient.query`: `returnTyped` — **FINAL cross-language v0.4.0 CP; SDK typed surface COMPLETE on both sides** |

---

## v0.2.0 Release (CP-83 → CP-85)

| CP | Commit | Status | Category | Subject |
|---|---|---|---|---|
| CP-83 | `e61e34f` | ✅ done | release | v0.2.0 release: CHANGELOG entries + version bumps both SDKs (10 files) |
| CP-84 | `867e590` | 📝 docs | docs | Root `CHANGELOG.md` SDK releases section + LOCAL v0.2.0 annotated tag at e61e34f |
| CP-85 | `26a1d29` | 📝 docs | docs | `docs/15_build_plan/SDK_RELEASE_RUNBOOK.md` + `release.yml` YAML lint validation |

---

## Summary statistics

| Bucket | Count |
|---|---|
| Distinct CP numbers (CP-01 → CP-85) | 85 plus sub-CPs |
| Total git commits in repo | 168 |
| ✅ feat commits | ~115 |
| 🔧 fix commits | ~18 |
| 📝 docs commits | ~25 |
| chore commits | ~10 |
| Python pytest at end-of-CP-85 | 1883 (100% line + branch coverage) |
| TypeScript vitest at end-of-CP-85 | 272 (100% coverage on `src/`) |
| Combined session test count | **2155** |

---

## How to use this ledger

- **At session start:** scan for the most recent CP in the table; verify `git log -1 --oneline` matches its commit hash; verify the green-signals block in `SESSION_EXPORT_2026-05-12.md` still passes.
- **Before starting a new CP:** add a planned row to `PHASE_ROADMAP_FUTURE.md` (NOT this file). This file is append-only and reflects what's actually committed.
- **After each commit:** append a row here with the commit hash, status, category, and one-line subject.
- **Sub-CPs (e.g. CP-10.1.tests, CP-10.1.fix) are preserved** because they encode the order in which a complex CP landed and what each commit contributed.
