# ADR-0001 — In-memory `Protocol`-typed stores for Phase 0 (vs Postgres)

- **Status:** Accepted
- **Date:** 2026-04-12
- **Phase:** 0 (hackathon prototype)
- **Decision owner:** v_sen
- **Affects:** Audit ledger, workflow / agent / tool registry, replay bundle store, dossier store

## Context

Verixa's production design (Phase 1+) targets:

- **Postgres** for the audit ledger and registry data (7 schemas: tenancy, registry, policy, runtime, audit, replay, compliance)
- **MinIO / S3** for replay bundles (large blobs, signed, AES-256-GCM sealed)
- **Redis** for the policy-bundle cache

For Phase 0 (4-week hackathon prototype) we need to demonstrate the *governance flows* — gateway → firewall → policy → risk → triad → audit → replay → dossier — without burning the timeline on Postgres migrations, MinIO bucket policies, or Redis cluster bootstrap. We also need the entire system to fit in a **single Hugging Face Space container** (Docker, ~1 GB image, free tier) so a judge can click one link and see it work.

A second constraint: we need to be able to **swap to real persistence in Phase 1 without rewriting any business logic or breaking any wire contract**. Hackathon code that becomes "throwaway" because the abstractions were wrong is a known failure pattern.

## Decision

Implement every persistence-bearing module as a **`typing.Protocol`-typed interface** with two implementations:

1. **`InMemory*` class** — Phase 0 default; uses Python dicts + lists; resets on process restart
2. **`Postgres*` / `Minio*` class** — Phase 1; same interface; same call sites

The runtime is wired against the **Protocol**, not against a concrete class. The choice of implementation is made at container start via dependency-injection. Phase 0 hard-codes `InMemoryAuditLedger`, `InMemoryRegistry`, `InMemoryReplayBundleStore`, `InMemoryDossierStore`. Phase 1 will flip those to their `Postgres*` / `Minio*` counterparts via environment variable.

Concrete files:

- `apps/runtime/verixa_runtime/audit/protocol.py` defines `AuditLedger` protocol; `in_memory.py` implements it
- `apps/runtime/verixa_runtime/replay/store.py` defines `ReplayBundleStore` protocol; `in_memory_store.py` + `minio_store.py` both implement it (MinIO test runs as gated integration test in CI)
- All Control-Plane API handlers accept the protocol type, never the implementation type

## Consequences

### Positive

- **Single-container demo works.** No external services to bootstrap. HF Space boots clean.
- **Tests are fast.** 1055 pytest in ~7s because nothing hits a real DB.
- **Phase 1 swap is mechanical.** The MinIO store already exists in `replay/minio_store.py` with the same protocol — verified by `test_replay_store_minio_integration.py` (gated; runs against a real MinIO container when Docker is available).
- **100% coverage achievable** because every branch is reachable from in-memory tests.

### Negative

- **No persistence across container restarts** in Phase 0. The seeded demo re-runs on every boot. Acceptable because the demo is the demo, not real customer data.
- **Memory is the only bound on ledger size.** Acceptable in Phase 0; Phase 1 Postgres has its own partitioning strategy (deferred to ADR-0006).
- **No concurrent multi-process access.** The in-memory store uses a single `asyncio.Lock`; multi-worker uvicorn would split the ledger. Acceptable because Phase 0 runs as a single worker.
- **Integration coverage of the persistence layer is light.** Only one gated test exercises the MinIO path; Postgres path has zero integration tests in Phase 0. Phase 1 will need a full integration matrix.

### Mitigations

- The Protocol interface is **frozen** for Phase 0 — no new methods land without a parallel change to both `InMemory*` and the Phase-1 stub. This prevents drift.
- The gated MinIO integration test runs in CI when Docker is available, catching at least the most common Phase-1 path before Phase 1 starts.
- All seeded demo data is regenerable from `demo_seed.py` on every boot, so "no persistence" doesn't mean "no determinism."

## Alternatives considered

1. **Postgres in the Phase-0 container** — rejected. Pushes the image size past HF Spaces free-tier limits, adds Alembic migration complexity to a 4-week timeline, and the demo doesn't need persistence to prove the flows.
2. **SQLite as a middle ground** — rejected. Either we commit to Postgres semantics (and SQLite drifts) or we commit to in-memory simplicity. SQLite is the worst of both: it pretends to be persistent but its dialect quirks don't match Phase 1.
3. **Skip persistence entirely** (no Protocol interface, just stateful classes) — rejected. Phase 1 would require rewriting every call site. The Protocol cost is ~30 minutes per module and pays back the first time we swap an implementation.

## Verification

- All persistence modules import from `protocol.py` and are typed against the Protocol — verified by `mypy --strict`
- `test_replay_store_minio_integration.py` proves the Phase-1 swap works on the replay store
- The README's "Phase 0 vs Phase 1" table calls this out explicitly so a buyer or auditor isn't surprised

## Related

- BRD: BR-03 (decision replay), BR-05 (cryptographic erasure)
- Traceability: `docs/17_traceability_matrix/TRACEABILITY_MATRIX.md` — every replay test
- Will be superseded in part by: ADR-0006 (Postgres schema partitioning, Phase 1)
