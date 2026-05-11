# Changelog

All notable changes to Verixa are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project will adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
from Phase 1 onwards. Phase 0 is pre-versioned and tracked by commit + checkpoint.

The Verixa platform itself is still Phase 0 (pre-release). The **SDKs** carry their own
SemVer versions because customers depend on them independently of the platform release
cadence. SDK release notes live in `packages/verixa-python/CHANGELOG.md` and
`packages/verixa-ts/CHANGELOG.md`; this file links to each SDK release tag.

---

## SDK releases

### v0.2.0 — 2026-05-12 (typed-response surface)

First versioned SDK release with the full typed-response surface + corrected
request schemas. Released in lockstep across both SDKs (matching the CP-59
release pipeline design):

- `verixa@0.2.0` (Python; PyPI) — full notes in `packages/verixa-python/CHANGELOG.md`
- `@verixa/ts@0.2.0` (TypeScript; npm) — full notes in `packages/verixa-ts/CHANGELOG.md`

Highlights:
- 15 typed envelope dataclasses (Python) / 14 typed interfaces (TS) mirroring every
  server-side response envelope
- Opt-in `return_typed=True` / `returnTyped: true` overloads on all 11 resource-client
  methods that have typed envelopes; default behaviour unchanged for full v0.1.0
  backward compatibility
- 4 wire-format request-side bugs fixed in the v0.1.0 alpha (Workflows.register,
  Agents.register, Tools.register, Dossier.generate); without these fixes every
  v0.1.0 call site would 422 against the real server
- `InvalidEnvelopeError` exception with `field {name}: ...` prefix matching across
  both SDKs for cross-language debuggability

### v0.1.0 — 2026-05-11 (alpha)

First public alpha of both SDKs. Async clients covering all routes wired through
Phase-1 CP-49.

---

## [Unreleased] — Phase 0 (hackathon prototype)

### CP-29 — Market-standard documentation pack (2026-05-11)
- Added `SECURITY.md` — vulnerability disclosure policy, supported versions, scope
- Added `CONTRIBUTING.md` — Phase 0 scope, dev environment, commit conventions
- Added `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1
- Added `CHANGELOG.md` — this file
- Next: ADRs (CP-29b), SBOM + NOTICE (CP-29c), API style guide (CP-29c)

### CP-28 — Negative test plan (2026-05-11)
- Added `docs/16_testing_and_qa/NEGATIVE_TEST_PLAN.md`
- Measured **31% negative-test coverage** (332 of 1055 pytest tests) — industry norm 30–40% for security products
- Documented 10 known gaps with target phase per category (Phase 0 stretch → Phase 2)

### CP-27 — BRD + user stories + traceability matrix (2026-05-11)
- Added `docs/02_brd/BRD.md` with BR-01 → BR-08 + acceptance criteria
- Added `docs/05_use_cases_and_user_stories/USER_STORIES.md` (job-stories format, US-01 → US-10)
- Added `docs/17_traceability_matrix/TRACEABILITY_MATRIX.md` (BR ↔ UC ↔ Test ↔ Code)
- Swept **25 doc-path references** across **21 files** to align with the new canonical numbering
- Fixed 4 phantom doc paths that had never existed in any numbering scheme

### CP-26 — Canonical docs/ renumbering (2026-05-11)
- Renamed **17 folders** under `docs/` via two-stage tmp-prefix `git mv` (history preserved)
- New canonical 20-slot order: Vision → BRD → Use Cases → Regulatory → Architecture → Build → Tests → Operations → Reference
- Use cases promoted from slot 02 (next to commercial) to slot 05 (between regulatory and architecture)
- Security architecture (10) now before threat model (11)
- Reusable renumber script kept at `_backup/renumber_docs_cp26.py`

### CP-25.1 — USE_CASES test-path correction (2026-05-11)
- Fixed 6 invented test names + paths in `USE_CASES.md` after a `Test-Path` check showed 4 of 6 were wrong
- Lesson encoded: ground every "Verified by" anchor in an actual `ls`, not memory

### CP-25 — USE_CASES.md with mermaid diagrams (2026-05-11)
- Added `docs/02_use_cases/USE_CASES.md` (later moved to `05_use_cases_and_user_stories/` in CP-26)
- 10 use cases (UC-01 → UC-10) with sequence diagrams in mermaid
- Every UC anchored to a real test and a working endpoint or seeded data record

### CP-23 — README polish for hackathon judging (2026-05-11)
- Honest Phase 0 vs Phase 1 deviation table
- Corrected reviewer triad row from "Qwen3-72B + Llama-3.3-70B + DeepSeek-V3" to actual "Qwen3-0.6B × 3 with distinct system prompts"
- Removed Phase 1 stack rows that didn't ship in the running container
- Test + coverage badges replace placeholders

### CP-22 — Dashboard fetch-cache fix (2026-05-11)
- Added `cache: 'no-store'` to `apps/control-plane-ui/src/lib/api-client.ts`
- Next.js Server-Component default caching was returning stale empty audit responses
- Caught by Playwright `dashboard.spec.ts` in CP-21

### CP-21.2 — GitHub Actions CI (2026-05-11)
- 3 parallel jobs: `python-tests` + `typescript` + `playwright`
- Cross-platform Playwright config via `VERIXA_UVICORN_CMD` env override
- YAML linter at `_backup/lint_ci_workflow.py`

### CP-21 — Playwright E2E + asgi bug fix (2026-05-11)
- 18 Playwright specs against the live FastAPI + Next.js dev server
- **Caught real shipping-blocker** in `apps/control-plane-api/verixa_control_plane/asgi.py` — uvicorn imports modules from inside a running asyncio loop, so `asyncio.run()` at module level crashes; fixed by spawning a fresh `threading.Thread` whose target calls `asyncio.run(...)`

### CP-17.2 — Hugging Face Space LIVE (2026-05-11 08:36 UK)
- Pushed to <https://huggingface.co/spaces/vsenthil7/verixa-control-plane>
- Public Swagger UI at `/docs` — every endpoint working
- Smoke test 17/17 PASS via `_backup/smoke_test_hf_space.py`
- README updated with live URL

### CP-17 — HF Spaces Dockerfile + ASGI entry (2026-05-10)
- `deploy/huggingface/Dockerfile` + `build_space_repo.py`

### CP-16 — Financial-services demo seed (2026-05-10)
- One workflow, one agent, four tools, three historical decisions, one pre-signed Ed25519 dossier
- Container boots pre-loaded so judges hit realistic data on the first click

### CP-1 through CP-15 — Core platform build (2026-04 → 2026-05)
- Cryptographic primitives (Ed25519 / AES-256-GCM / SHA-256 hash chain)
- Append-only audit ledger + offline verifier
- FastAPI gateway with structured logging
- Tool Firewall (allow-list + arg bounds)
- OPA-based Policy Engine with signed bundles + Redis cache
- Risk Engine + Router (allow / deny / escalate)
- Triad Review Engine (commit-reveal protocol, 3 reviewers)
- Replay Vault (AES-256-GCM sealed bundles, MinIO Phase-1 ready)
- Compliance Dossier Generator (Ed25519 signed, verifies offline)
- Control Plane API (7 routes) + Next.js 14 UI (4 pages)
- 1055 pytest + 35 vitest + 18 Playwright at 100% line + branch coverage

---

## Versioning policy

Phase 0 is **pre-release**. Once Phase 1 ships, semver applies:

- **MAJOR** — breaking changes to the audit / dossier wire format (rare; needs migration path)
- **MINOR** — new endpoints, new features, additive schema changes
- **PATCH** — bug fixes, doc fixes, dependency bumps

The audit / dossier formats will carry their own `format_version` field independent of the codebase version — this is the durable contract for offline verifiers.
