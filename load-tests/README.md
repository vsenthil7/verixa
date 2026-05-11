# Verixa Load Tests

> Load tests live separately from the unit/integration test suite because they
> have different goals, different cadence, and different infrastructure
> requirements. The unit/integration suite asserts **correctness**; the load
> tests assert **survivability under volume**.

## What lives here

- **`README.md`** (this file) — what load tests we maintain, how to run them
- **`baseline/`** — Phase 0 reference numbers + the test code that produced them
- **`scenarios/`** — concrete load scenarios per BR (filled out as needed)

## When to run

- **CI:** load tests are NOT in the default CI gate (would slow it to a crawl).
  A nightly job runs them against a fresh pre-prod environment.
- **Pre-release:** mandatory pre-release run; outcomes recorded against the
  SLO/SLA Specification's per-tier targets.
- **Post-incident:** if an incident retrospective traces back to load-related
  causes, run the relevant scenario in pre-prod to validate the fix.

## Phase 0 baseline (recorded 2026-05-11)

The Phase 0 baseline tests are limited by the in-memory architecture — they
don't exercise Postgres / MinIO / SPIFFE / Vault. The numbers below establish
a *correctness-under-load* floor, not a production-realistic load.

| Scenario | Metric | Phase 0 result | Target (Tier 4 Pro SLO) |
|---|---|---|---|
| InMemoryAuditLedger concurrent appends (CP-38 unit-test territory) | 1000 concurrent appends settled | < 1 second | n/a (in-memory only) |
| InMemoryBundleStore + InMemoryAuditIndex via Snapshotter (CP-38) | 50 concurrent snapshots | < 0.5 seconds | n/a (in-memory only) |
| Sustained-rate governed decisions (CP-42 below) | 1000 audit-ledger appends in single batch | 100% completion, zero errors, sub-second | 100/sec sustained per replica = baseline; production target 500/sec/replica |

These baseline numbers are intentionally conservative: the goal is to prove
the in-memory infrastructure does not silently drop work under load.
Production numbers (with Postgres + MinIO) will be measured separately in
Phase 1.

## How to run

```powershell
cd C:\path\to\verixa
.\.venv\Scripts\python.exe -m pytest load-tests/ --no-cov -v
```

Load tests are excluded from the default CI test suite via the
`pyproject.toml` `norecursedirs` directive (introduced in CP-32). They run
only when invoked explicitly with the `load-tests/` path.

## Phase 1+ roadmap

| Scenario | Effort | Owner |
|---|---|---|
| Postgres-backed audit ledger sustained-rate test (10k decisions/min for 1 hour) | MEDIUM | SRE |
| MinIO-backed replay vault concurrent-snapshot throughput (target 1000 snapshots/min) | MEDIUM | SRE |
| Triad-orchestration latency under 100 concurrent /govern calls (target p99 < 5s end-to-end) | MEDIUM | Eng + SRE |
| Chaos-engineering scenarios (random pod kills, network partition, DB failover) | HIGH | SRE |
| Multi-tenant noisy-neighbour isolation tests | MEDIUM | SRE |
| Sustained 24-hour soak test on Tier 3/4 pre-prod | HIGH | SRE |

## References

- `docs/18_sre_and_operations/SLO_SLA_SPECIFICATION.md` — per-tier targets the
  load tests must prove
- `docs/19_incident_response_plan/DISASTER_RECOVERY_PLAN.md` §3 — RTO/RPO
  targets validated by load + chaos testing
- `docs/16_testing_and_qa/NEGATIVE_TEST_PLAN.md` — adversarial coverage that
  these load tests extend (CP-38 race conditions are *correctness* tests; the
  Phase 0 baseline test below is the *volume* equivalent)
