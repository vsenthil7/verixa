# Verixa

> Enterprise AI runtime governance platform.
> Intercepts, verifies, governs, audits, and replays AI-driven actions
> before they affect the real world — and produces evidence to demonstrate
> that the action was governed.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Phase](https://img.shields.io/badge/phase-0%20%E2%80%94%20hackathon%20prototype-blue)](docs/10_build_plan/BUILD_PLAN.md)
[![Track](https://img.shields.io/badge/track-AI%20Agents%20%26%20Agentic%20Workflows-purple)]()
[![GPU](https://img.shields.io/badge/GPU-AMD%20MI300X%20%2B%20ROCm-red)]()
[![Tests](https://img.shields.io/badge/tests-1055%20pytest%20%2B%2035%20vitest%20%2B%2018%20playwright-brightgreen)]()
[![Coverage](https://img.shields.io/badge/coverage-100%25%20line%20%2B%20branch-brightgreen)]()

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
   their verdicts via a hash-commit-and-reveal protocol *before* any verdict
   is revealed; consensus is computed across them
5. **Records** every step in an append-only, hash-chained, Ed25519-signed
   audit ledger
6. **Snapshots** enough context to reconstruct the decision later
   (snapshot-based replay; not bit-exact regeneration)
7. **Generates** Annex IV-aligned runtime technical dossiers on demand,
   signed with Ed25519 and **verifiable offline** without trusting Verixa

The output is **evidence that supports demonstrating** an AI-driven action
was governed — not a claim that the action is provably correct.

---

## See it working in 30 seconds

The simplest demo. No dependencies beyond Docker + Python 3.12:

```bash
docker build -f deploy/huggingface/Dockerfile -t verixa-cp .
docker run -p 7860:7860 verixa-cp
# then open http://localhost:7860/docs
```

That's the same image the public Hugging Face Space runs. The container
boots **pre-loaded with a small-bank loan-approval scenario**: one workflow,
one agent, four tools, three historical decisions across the risk spectrum,
one pre-signed Ed25519 dossier. Every endpoint at `/docs` has a *Try it
out* button and returns realistic data on the first click.

Flows to try (in this order):

1. `GET /v1/control/workflows` — see the seeded workflow with its agent
   count and risk-threshold settings.
2. `GET /v1/control/audit?workflow_id=<id>&from=...&to=...` — three
   seeded decisions: a low-risk customer lookup (ALLOW), a medium-risk
   USD 12,500 transfer escalated to triad consensus (ALLOW), and a
   high-risk USD 95,000 transfer to an unverified beneficiary (DENY).
3. `POST /v1/control/replay` — pass an `audit_id` from step 2 and get
   the full reconstructed decision context back: request envelope,
   policy evaluations, triad verdicts + commitments.
4. `POST /v1/control/dossier` — generate a signed evidence pack for
   any audit_id.
5. `GET /v1/control/dossier/{id}` — fetch the signed dossier. The
   `signature_hex` and `public_key_hex` fields verify the manifest
   with any standard Ed25519 verifier — Verixa is **not in the trust
   path**.

---

## Architecture

24 modules across 4 groups; Phase 0 implements the governance hot path:

**Core Runtime (7):** Runtime Gateway · Tool Call Firewall · Policy Engine
(OPA+Rego) · Risk Engine · Decision Router · Audit Ledger · Replay Vault

**AI Verification (Phase 0 subset):** Triad Review Engine · Evidence
Validator

**Enterprise Control (Phase 0 subset):** Compliance Dossier Generator
(per-decision pack) · Control Plane API (FastAPI) · Control Plane UI
(Next.js 14)

Phase 1+ modules (Approval Matrix, Contradiction Detector, Hallucination
Risk Engine, Drift Monitor, Trust Graph, Bench, Hallmark, Forge, Replica,
Mesh, WET Ops) are **architecturally present but not implemented** in
Phase 0.

Full architecture: [`docs/04_architecture/ARCHITECTURE.md`](docs/04_architecture/ARCHITECTURE.md)

---

## Tech stack

| Layer | Tech |
|---|---|
| Compute | AMD Instinct MI300X (192 GB HBM3) via AMD Developer Cloud |
| GPU runtime | ROCm 7.x + PyTorch + Optimum-AMD |
| Inference | vLLM-on-ROCm (OpenAI-compatible serving) |
| Reviewer triad (Phase 0) | Qwen3-0.6B × 3 with distinct system prompts (conservative / pragmatic / sceptical) — protocol is model-agnostic; Phase 1 swaps to three larger heterogeneous models without code changes |
| Backend | FastAPI + Python 3.12 + Pydantic v2 |
| Persistence (Phase 0) | In-memory Protocol-typed stores; Phase 1 swaps for Postgres 16 + pgvector + MinIO without API changes |
| Frontend | Next.js 14 + React 18 (Server Components) |
| Crypto | SHA-256 + Ed25519 + AES-256-GCM |
| Policy | OPA + Rego (signed bundles) |
| Identity | SPIFFE/SPIRE (Phase 0: bypassed; Phase 1 ready) |
| Tests | pytest + Vitest + Playwright + Hypothesis + Schemathesis |

---

## Phase 0 honesty

Phase 0 is a hackathon prototype. Here's exactly what's deviated from
production-grade and where the production path is:

| Concern | Phase 0 | Phase 1 path |
|---|---|---|
| Reviewer triad models | Qwen3-0.6B × 3, distinct system prompts | Three larger heterogeneous models (e.g. Qwen3-72B + Llama-3.3-70B + DeepSeek-V3) — protocol is model-agnostic |
| Persistence | In-memory `Protocol`-typed stores | Postgres 16 + pgvector + MinIO — same `Protocol` interfaces, drop-in replacement |
| SPIFFE / agent identity | Bypassed in dev mode; SPIFFE ID recorded for audit | Real SPIRE workload attestation |
| Secrets | Ed25519 signing key minted at container start | HashiCorp Vault Transit + KMS-backed key wrapping |
| Multi-tenancy | Per-tenant AES keys; cryptographic erasure via key zeroisation works today | Per-tenant Postgres row-level security + Vault namespace isolation |
| Compliance language | "Annex IV-aligned" not "regulator-ready"; "evidence supports demonstrating" not "proves" — hardened throughout source comments + commit messages + this README | Same posture, with formal independent review |

---

## Quickstart (developing locally)

> **Prerequisites:** Python 3.12, Node 22, Poetry, pnpm. Docker optional
> (only needed for the gated MinIO/Redis integration tests).

```bash
# clone
git clone https://github.com/v-sen/verixa.git verixa
cd verixa

# install Python deps
poetry install

# install Node deps
pnpm install

# run the full test suite (unit only; integration tests gated)
poetry run pytest -m 'not integration'         # 1055 tests
cd apps/control-plane-ui && pnpm test:coverage  # 35 tests
pnpm exec playwright test                       # 18 E2E specs

# start the dev stack
poetry run uvicorn verixa_control_plane.asgi:app --port 8001
# (in another terminal)
cd apps/control-plane-ui && pnpm dev
# open http://localhost:3000
```

---

## Tests

| Suite | Count | Coverage | Runtime |
|---|---|---|---|
| Python unit (pytest) | 1055 | 100% line + branch on 60 modules | ~10 s |
| TypeScript unit (vitest) | 35 | 100% on api-client.ts + design.ts + config.ts | ~1 s |
| Browser E2E (Playwright + Chromium) | 18 | All 4 UI pages × happy + error paths | ~19 s |
| Live MI300X triad (gated `pytest -m integration`) | 4 | Protocol invariants, not specific decisions | ~5 s when MI300X is up |
| Container testcontainers (gated) | 3 | 1 Redis + 2 MinIO round-trip | ~30 s when Docker is up |

The 100% coverage gate is enforced — Python via `fail_under=100` in
`pyproject.toml`, TypeScript via vitest thresholds. The Playwright suite
caught a real shipping-blocker bug in the production ASGI entry point
during CP-21; that fix is documented at
[`apps/control-plane-api/verixa_control_plane/asgi.py`](apps/control-plane-api/verixa_control_plane/asgi.py).

CI: GitHub Actions runs all three suites on every push and pull request to
`main`. Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Hackathon submission

- **Track:** AI Agents & Agentic Workflows (Track 1)
- **Compute:** AMD Developer Cloud, MI300X droplet
- **Cross-cutting prizes targeted:**
  - Hugging Face Special Prize — HF Spaces deployment + Hub model use
  - Qwen Special Reward — Qwen3 family powers the reviewer triad
  - Build-in-Public — public repo with full granular commit history
- **Live demo:** _(HF Space URL — pending CP-17.2 deploy)_
- **Demo video:** _(YouTube URL — pending CP-19)_
- **Submission:** _(lablab.ai URL — pending CP-20)_

---

## Documentation

The full architecture and operations pack lives under [`docs/`](docs/).
Highlights for first-time readers:

- [`docs/04_architecture/ARCHITECTURE.md`](docs/04_architecture/ARCHITECTURE.md) — 24 modules, 4 groups, dependency graph
- [`docs/09_evidence_pack/EVIDENCE_PACK_SPEC.md`](docs/09_evidence_pack/EVIDENCE_PACK_SPEC.md) — dossier structure, signing, offline verification
- [`docs/12_security_compliance/SECURITY_COMPLIANCE.md`](docs/12_security_compliance/SECURITY_COMPLIANCE.md) — threat model, EU AI Act / GDPR mapping
- [`docs/17_glossary/GLOSSARY.md`](docs/17_glossary/GLOSSARY.md) — terms of art and compliance-language hardening rules

---

## Compliance-language posture

Verixa **does not claim** to make AI actions provably correct,
regulator-ready in a formal sense, or bit-exactly reproducible. Verixa
**does claim** to produce evidence that supports demonstrating an
AI-driven action was governed — under a signed policy, with a
hash-chained audit trail, with snapshot-based replay, and with an
Annex IV-aligned runtime technical dossier on demand.

The distinction matters for buyers and for regulators. The README, source
comments, demo script, and submission materials are all written under
this hardened-language discipline. See
[`docs/17_glossary/GLOSSARY.md`](docs/17_glossary/GLOSSARY.md) for the
full rule set.

---

## Originality

Verixa builds on lessons learned from earlier projects by the same author
(Auditex / Hack0014; SwarmScout / Hack0015). Where shared patterns appear,
those projects are referenced as MIT-licensed dependencies, not copied
verbatim. Verixa is original work for AMD Hack0017.

---

## License

MIT — see [LICENSE](LICENSE).
