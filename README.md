# Verixa

> Enterprise AI runtime control plane and trust platform.
> Intercepts, verifies, governs, audits, replays, and creates evidence to
> demonstrate and support AI-driven actions before and after they affect the
> real world.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Phase](https://img.shields.io/badge/phase-0%20%E2%80%94%20hackathon%20prototype-blue)](docs/10_build_plan/BUILD_PLAN.md)
[![Track](https://img.shields.io/badge/track-AI%20Agents%20%26%20Agentic%20Workflows-purple)]()
[![GPU](https://img.shields.io/badge/GPU-AMD%20MI300X%20%2B%20ROCm%207.x-red)]()

---

## What Verixa is

Verixa sits **between an AI agent and the world it acts on**. Every governed
action — every tool call, every model output bound for a real-world side
effect — passes through a runtime gateway that:

1. **Validates** the action against a signed policy bundle (OPA + Rego)
2. **Scores** the action's risk against workflow + agent + tool context
3. **Routes** the action: allow, deny, escalate to human, or escalate to a
   reviewer triad of independent AI models
4. **Verifies** (when the triad is invoked): three reviewer models commit
   their verdicts via a hash-commit-and-reveal protocol before any verdict is
   revealed; consensus is computed across them
5. **Records** every step in an append-only, hash-chained, Ed25519-signed
   audit ledger
6. **Snapshots** enough context to reconstruct the decision later
   (snapshot-based replay; not bit-exact regeneration)
7. **Generates** Annex IV-aligned runtime technical dossiers on demand

The output is **evidence to demonstrate and support** that an AI-driven
action was governed — not a claim that the action is provably correct.

---

## Architecture (Phase 0 scope)

24 modules across 4 groups; Phase 0 implements the hot path:

**Core Runtime (7):** Runtime Gateway · Tool Call Firewall · Policy Engine
(OPA+Rego) · Risk Engine · Decision Router · Audit Ledger · Replay Vault

**AI Verification (Phase 0 subset):** Triad Review Engine · Evidence
Validator

**Enterprise Control (Phase 0 subset):** Compliance Dossier Generator
(per-decision pack) · Control Plane API skeleton · Next.js UI

Phase 1+ modules (Approval Matrix, Contradiction Detector, Hallucination Risk
Engine, Drift Monitor, Trust Graph, Bench, Hallmark, Forge, Replica, Mesh,
WET Ops) are **architecturally present but not implemented** in Phase 0.

Full architecture: [`docs/04_architecture/ARCHITECTURE.md`](docs/04_architecture/ARCHITECTURE.md)

---

## Tech stack

| Layer | Tech |
|---|---|
| Compute | AMD Instinct MI300X (192 GB HBM3) via AMD Developer Cloud |
| GPU runtime | ROCm 7.x + PyTorch + Optimum-AMD |
| Inference | vLLM-on-ROCm (OpenAI-compatible serving) |
| Reviewer triad | Qwen3-72B + Llama-3.3-70B + DeepSeek-V3 |
| Backend | FastAPI + Python 3.12 + Pydantic v2 + SQLAlchemy 2.0 async |
| Database | Postgres 16 + pgvector |
| Background jobs | Celery + Redis |
| Frontend | Next.js 14 + React 18 + Tailwind + shadcn/ui |
| Crypto | SHA-256 + Ed25519 + AES-256-GCM |
| Policy | OPA + Rego |
| Identity | SPIFFE / SPIRE (dev: bypassed; documented for Phase 1) |
| Secrets | HashiCorp Vault (dev mode) |
| Container | Docker Compose (dev) + Helm charts (prod-ready, not deployed Phase 0) |
| Tests | pytest + Vitest + Playwright + Hypothesis + Schemathesis |

---

## Quickstart (dev)

> **Prerequisites:** Docker Desktop, Python 3.12, Node 20+, Poetry, pnpm.

```bash
# clone
git clone <repo-url> verixa
cd verixa

# bring up the dev stack (Postgres, Redis, OPA, Vault dev, MinIO, Prometheus stub)
make up
make health

# install Python deps + run migrations
poetry install
poetry run alembic upgrade head

# install Node deps + build UI
pnpm install
pnpm --filter control-plane-ui dev

# run tests
make test
```

PowerShell users: `./ops.ps1 up`, `./ops.ps1 health`, `./ops.ps1 test`.

---

## Hackathon submission

- **Track:** AI Agents & Agentic Workflows (Track 1)
- **Cross-cutting prizes targeted:**
  - Hugging Face Special Prize — HF Spaces deployment + HF Hub model use + HF Datasets policy library
  - Qwen Special Reward — Qwen3-72B as one of three reviewer models
  - Build-in-Public — public repo with full commit history
- **Live demo:** _(HF Space URL — pending CP-17)_
- **Demo video:** _(YouTube URL — pending CP-19)_
- **Submission:** _(lablab.ai URL — pending CP-20)_

---

## Documentation

The full 17-document architecture and operations pack lives under [`docs/`](docs/):

| # | Document | Purpose |
|---|---|---|
| 01 | Vision & Positioning | Product positioning, market gap, AAGATE alignment |
| 02 | Use Cases | UC-01 through UC-08 canonical scenarios |
| 03 | Domain Model | Glossary, entities, relationships |
| 04 | Architecture | 24 modules, 4 groups, dependency graph |
| 05 | API Specification | Runtime + Control Plane endpoint contracts |
| 06 | Data Model | Postgres schemas (tenancy, registry, policy, runtime, audit, replay, compliance) |
| 07 | Policy Specification | OPA + Rego policy structure, signing, distribution |
| 08 | Risk Engine | Composite scoring + Trust Graph (Phase 4) |
| 09 | Evidence Pack Specification | Dossier structure, manifest, offline verification |
| 10 | Build Plan | Phase 0 → Phase 6 module sequencing |
| 11 | Deployment | Sovereign deployment options, Tier 1/2/3 capacity |
| 12 | Security & Compliance | Threat model, Article 14 mapping, GDPR / EU AI Act |
| 13 | Observability | Logs, metrics, traces, SLOs |
| 14 | Operations | Runbooks, incident response, key rotation |
| 15 | Testing & QA | Test scope, coverage targets, hot-path discipline |
| 16 | Roadmap | Phase 1+ commitments and deferrals |
| 17 | Glossary | Terms of art and compliance-language hardening rules |

---

## Compliance-language posture

Verixa **does not claim** to make AI actions provably correct, regulator-ready
in a formal sense, or bit-exactly reproducible. Verixa **does claim** to
produce evidence that supports demonstrating an AI-driven action was governed
— under a signed policy, with a hash-chained audit trail, with snapshot-based
replay, and with an Annex IV-aligned runtime technical dossier on demand.

The distinction matters for buyers and for regulators. The README, source
comments, demo script, and submission materials are all written under this
hardened-language discipline.

---

## Status

**Phase 0 — hackathon prototype.** Built against the locked architecture and
documentation pack from AT-Hack0017-002. Submission deadline 2026-05-10
20:00 BST.

Local commit history is canonical during build; remote push pending GitHub
account resolution. Build-in-public commit history is preserved verbatim.

---

## Originality clause

Verixa builds on lessons learned from earlier projects by the same author
(Auditex / Hack0014; SwarmScout / Hack0015). Where shared patterns appear,
those projects are referenced as MIT-licensed dependencies, not copied
verbatim. Verixa is original work for AMD Hack0017.

---

## License

MIT — see [LICENSE](LICENSE).
