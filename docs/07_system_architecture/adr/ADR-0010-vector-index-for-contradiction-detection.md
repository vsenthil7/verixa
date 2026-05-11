# ADR-0010 — Vector-index choice for contradiction detection (Phase 2)

- **Status:** Proposed (Phase 2 placeholder; included in Phase 1 docs work because the technology choice may need to be made earlier than Phase 2 implementation)
- **Date:** 2026-05-11
- **Phase:** 2 (contradiction detection rollout)
- **Decision owner:** TBD at Phase 2 kickoff
- **Affects:** UC-12 (contradiction detection), audit-query latency, cross-decision intelligence layer

## Context

Phase 2 introduces **UC-12 contradiction detection**: when a new governed decision is made, Verixa compares it against historical decisions on near-identical inputs and flags if the current decision contradicts past ones. Use case examples:

- A "transfer £10,000 to ACC-12345" gets DENIED today, but the same agent made the same transfer 6 months ago and it was ALLOWED. Why the inconsistency?
- Agent A and Agent B in the same workflow receive near-identical prompts and produce different actions. Drift signal.

The implementation requires:

1. **Embedding** every decision context (prompt + retrieved docs + action) into a vector space.
2. **Indexing** those vectors for fast approximate-nearest-neighbour (ANN) search at decision time.
3. **Threshold tuning** — what cosine-similarity threshold means "near-identical"?
4. **Per-tenant isolation** — Tenant A's vectors must not be searchable from Tenant B.
5. **GDPR-erasure compatibility** — when a tenant exercises BR-05 cryptographic erasure, their vectors must become unreachable.
6. **Scale** — 1M decisions per tenant, 1000 tenants = 1B vectors. ANN search at this scale is a real engineering problem.

Candidate technologies (mid-2026 landscape):

- **pgvector** (Postgres extension)
- **Qdrant** (Rust, gRPC + REST, self-hosted)
- **Milvus** (Go + C++, gRPC, self-hosted, Kubernetes-native)
- **Weaviate** (Go, gRPC + REST, self-hosted)
- **Cloud-managed: AWS OpenSearch Vector, GCP Vertex AI Vector Search, Azure AI Search**

## Decision (preliminary lean — Phase 2 will revisit with empirical data)

**Start with pgvector** for Phase 2 MVP. Reasons:

1. **No new operational system.** Audit ledger already lives in Postgres (per ADR-0006); pgvector is a Postgres extension, not a new service.
2. **Per-tenant isolation comes for free** via the same partitioning scheme as the audit ledger.
3. **Erasure semantics are clear** — destroying a tenant's partitions destroys their vectors.
4. **Joins with audit metadata stay in SQL** — "find decisions similar to X that were DENIED in the last 30 days" is one query, not two systems.

**Migrate to Qdrant or Milvus** if Phase 2 benchmarks show pgvector falls over at the 1B-vector scale, OR if Phase 3 cross-cloud federation (ADR-future) requires a purpose-built vector DB.

Final decision deferred. Phase 2 prototype will measure pgvector against Qdrant on a 100M-vector synthetic dataset before locking in.

## Consequences

### Positive

- **One persistence system instead of two.** Operators learn one set of backup, replication, monitoring tools.
- **Per-tenant erasure is free.** Same partitioning + DEK story as the audit ledger.
- **Joins are SQL.** Cross-cutting queries ("find similar past decisions that the triad escalated") are one query.
- **pgvector quality is competitive** for sub-100M-vector workloads as of 2026 (HNSW + IVFFlat indexes match purpose-built systems within 2× recall at p95).

### Negative

- **pgvector at 1B+ vectors is uncharted.** Phase 2 must benchmark; if it falls over, migration to Qdrant/Milvus is non-trivial.
- **Embedding model choice is a separate decision** (not made in this ADR). The vector space's quality matters more than the index's quality; a bad embedding wastes any index optimisation.
- **Vector + audit-ledger sharing infrastructure** means a hot ANN query can interfere with audit-write latency. Phase 2 must monitor and may need read-replicas for ANN queries.

### Mitigations

- Phase 2 implementation uses a `VectorIndex` protocol (parallel to ADR-0001 persistence protocols). pgvector and Qdrant adapters both implement it; migration is the same shape as ADR-0001's in-memory-to-Postgres swap.
- The embedding model is pluggable via a separate `Embedder` protocol; swappable without touching the index.
- Phase 2 instruments ANN-query latency vs audit-write latency; alerts if either degrades the other.

## Alternatives considered

1. **Qdrant from day one.** Rejected for Phase 2 MVP because it introduces a new system before we know we need it. Will revisit at Phase 2 close if benchmarks demand it.
2. **OpenSearch / Elasticsearch with kNN plugin.** Rejected. Elasticsearch's licensing turbulence + the AWS fork divergence makes adoption risky for a multi-cloud product.
3. **Cloud-managed vector search.** Considered. Adds per-cloud lock-in; conflicts with Verixa's "deploy anywhere" posture. Useful for customers running purely in one cloud — likely a Phase-3 cloud-managed adapter.
4. **Vector search at all.** Rejected as alternative. UC-12 requires similarity search; exact-match SQL queries on prompt hashes catch only identical inputs, not near-identical.
5. **Use the existing prompt_hash as the similarity key.** Considered briefly. Rejected: prompt_hash is SHA-256 of canonical text; one whitespace difference = different hash. Semantic similarity needs embeddings.

## Verification

- Phase 2 MVP success: 10M-vector pgvector index returns top-10 similar past decisions in under 50ms p95 on commodity hardware.
- Per-tenant isolation: verified by integration test confirming no cross-tenant vector visibility.
- Erasure: destroying a tenant's DEK + partition makes their vectors unreachable; verified by gated integration test.

## Related

- UC-12 (contradiction detection) in `docs/05_use_cases_and_user_stories/USE_CASES.md`
- UC-13 (hallucination risk scoring) — uses similar embedding infrastructure
- BR-05 (cryptographic erasure)
- ADR-0001 (in-memory stores) — protocol pattern repeats here
- ADR-0006 (Postgres partitioning) — vector storage co-locates with audit storage in Phase 2
- `docs/16_testing_and_qa/NEGATIVE_TEST_PLAN.md` §9 — adversarial tests for contradiction detection will be added at Phase 2 implementation
