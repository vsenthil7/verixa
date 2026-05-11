# Architecture Decision Records (ADRs)

This folder contains ADRs — short, dated records of architectural decisions
that shaped Verixa. Format follows
[Michael Nygard's template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions):
**Context → Decision → Consequences (with explicit trade-offs)**.

## Why ADRs

Code shows *what* the system does. ADRs preserve *why* it does it that way.
A new engineer (or a Phase-1 auditor, or a buyer's security review) reading
the code in isolation cannot reconstruct the constraints and trade-offs
that drove a specific choice. ADRs fill that gap.

For Verixa specifically, ADRs are also the **audit-defensible record** of
choices that will eventually be challenged in compliance review — e.g.
"why Ed25519 and not RSA-4096?" or "why three Qwen3-0.6B reviewers instead
of three different model families?"

## Status conventions

- **Proposed** — under consideration; not yet implemented
- **Accepted** — implemented; the decision is in force
- **Deprecated** — superseded by a later ADR; the old approach is being phased out
- **Superseded by ADR-NNNN** — replaced; see the named ADR for the new decision

## Naming

`ADR-NNNN-short-slug.md` — zero-padded sequential number, never reused.
A superseded ADR keeps its number; a new ADR is added with a new number that
references it.

## Active ADRs (Phase 0)

| # | Title | Status | Date |
|---|---|---|---|
| [ADR-0001](ADR-0001-in-memory-stores-for-phase-0.md) | In-memory `Protocol`-typed stores for Phase 0 (vs Postgres) | Accepted | 2026-04-12 |
| [ADR-0002](ADR-0002-qwen3-06b-reviewer-triad.md) | Reviewer triad: Qwen3-0.6B × 3 with distinct system prompts | Accepted | 2026-04-18 |
| [ADR-0003](ADR-0003-commit-reveal-protocol-for-triad.md) | Commit-reveal protocol for triad consensus | Accepted | 2026-04-20 |
| [ADR-0004](ADR-0004-ed25519-over-rsa-for-dossier-signing.md) | Ed25519 over RSA for dossier signing | Accepted | 2026-04-15 |
| [ADR-0005](ADR-0005-mermaid-for-diagrams.md) | Mermaid for sequence/architecture diagrams (vs draw.io / PlantUML) | Accepted | 2026-05-11 |

## Phase-1 ADRs (placeholders, to be written when implementation starts)

- ADR-0006 — Postgres schema partitioning strategy for the audit ledger
- ADR-0007 — SPIRE workload attestation vs API-key tenant auth
- ADR-0008 — HashiCorp Vault vs cloud KMS for signing-key custody
- ADR-0009 — Approval-matrix (human-in-the-loop) routing rules
- ADR-0010 — Vector-index choice for contradiction detection (Phase 2)
