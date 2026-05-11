# ADR-0006 — Postgres schema partitioning strategy for the audit ledger

- **Status:** Proposed (Phase 1 placeholder)
- **Date:** 2026-05-11
- **Phase:** 1 (production rollout)
- **Decision owner:** TBD at Phase 1 kickoff
- **Affects:** Audit ledger, retention policy, replay query latency, compliance evidence

## Context

Phase 0 uses an `InMemoryAuditLedger` (ADR-0001). Phase 1 must persist the audit ledger to **Postgres** with the following constraints:

1. **Append-only.** Audit rows are never updated or deleted; cryptographic erasure (BR-05) is achieved by destroying per-tenant data encryption keys, not by deleting rows. Postgres-level partitioning must respect this.
2. **7-year retention minimum.** Most regulated buyers (financial services, healthcare, public sector) require minimum 7 years; some require 10. The hot/warm/cold tiering decision lives here.
3. **Decision-query latency.** The operator UI shows the last N days of decisions; the audit log query must return under 200ms even at 100M-row scale.
4. **Multi-tenant isolation.** Per-tenant queries must remain fast as the table grows; cross-tenant queries (rare, operator-only) are acceptable at higher latency.
5. **SHA-256 hash chain verification.** The standalone offline verifier (`tools/audit_verify.py`) must continue to work against partitioned data. Partition boundaries must not break the chain.

## Decision (preliminary lean)

**Partition by `(tenant_id, decision_timestamp_month)`** — composite range partitioning. Each partition is one tenant × one calendar month. Old partitions (>13 months) move to a `_archive_*` tablespace on slower storage. After 7 years, partitions move to S3-Glacier-equivalent cold storage with a metadata stub remaining in Postgres for query routing.

Per-tenant hash chain anchors: each partition starts a new sub-chain anchored to the previous partition's terminal hash. The standalone verifier walks the chain across partition boundaries by following these anchors.

Final decision deferred to Phase 1 kickoff after benchmarking against a realistic 100M-row synthetic dataset.

## Consequences

### Positive

- **Predictable query plans.** Tenant scoping is the most common access pattern; partition pruning makes it O(rows-in-the-relevant-month).
- **Cheap archival.** Moving a whole partition to cold storage is one ALTER TABLE; no row-level migration.
- **Erasure-compatible.** Per-tenant DEK destruction (BR-05) renders an entire tenant's partitions unreadable without touching Postgres.

### Negative

- **Partition explosion.** 1000 tenants × 84 months (7 years) = 84,000 partitions. Postgres handles this but `pg_dump`, query planner, and operator tooling slow down at that scale. Phase 1 must benchmark.
- **Cross-tenant queries cost more.** Operator-side aggregate queries ("how many DENY decisions across all tenants in Q1") become parallel scans across many partitions. Acceptable because these queries are rare and run async.
- **Schema migration is painful.** Adding a column to the audit table touches all 84,000 partitions. Postgres 12+ helps via partition-aware DDL; still slower than a single-table change.

### Mitigations

- Use **declarative range partitioning** (Postgres 11+) so partition management is automatic.
- Add a **partition-management daemon** as part of the Control Plane (creates next month's partition + archives old ones nightly).
- Standardise on schema-additive changes; use views to expose stable column sets to consumers.

## Alternatives considered

1. **Single non-partitioned table.** Rejected for 100M-row scale; index bloat + vacuum cost makes operator queries unpredictable.
2. **Partition by tenant only (no time dimension).** Rejected because archival requires a time dimension; without it the partition that contains a 7-year-old row is the same one that contains today's row.
3. **Partition by month only (no tenant dimension).** Rejected because per-tenant queries — the dominant pattern — scan every tenant in the month.
4. **Sharding across multiple Postgres instances.** Deferred to Phase 4 (cross-cloud federation). Adds operational complexity not justified by Phase 1 scale.
5. **Move to a purpose-built ledger DB (QLDB, Immudb).** Deferred. Postgres is well-understood; the audit chain is application-level not DB-level; switching ledger DBs is a Phase 2+ optimisation if Phase 1 benchmarks force it.

## Verification

- Phase 1 success criterion: 100M synthetic rows + 1000 synthetic tenants + per-tenant query under 200ms p95.
- Hash chain verification must still pass `tools/audit_verify.py` against partitioned data — covered by a new gated integration test in Phase 1.
- Operator dashboard "last 7 days" query must return under 100ms even on the largest tenant.

## Related

- ADR-0001 (in-memory stores) — this ADR supersedes the audit-ledger portion of ADR-0001 when Phase 1 ships
- BR-05 (cryptographic erasure)
- `docs/03_regulatory_and_compliance_baseline/REGULATORY_AND_COMPLIANCE_BASELINE.md` — 7-year retention norms across regulatory frameworks
- `tools/audit_verify.py` — standalone verifier that must continue to work post-partitioning
