---
title: Verixa Control Plane API
emoji: 🛡️
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Enterprise AI runtime governance — intercept, verify, audit
---

# Verixa Control Plane API

[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)]()
[![Tests](https://img.shields.io/badge/tests-1050%20passing-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

**Verixa intercepts, verifies, governs, audits, and replays AI-driven actions
before they affect the real world.**

This Hugging Face Space hosts the FastAPI Control Plane with a
pre-seeded financial-services demo scenario. Every endpoint is live
and returns realistic data on the first call.

## What this is

A Phase-0 hackathon prototype of the Verixa runtime governance
platform. The Control Plane API is the **operator-facing
surface**: where security teams register workflows, query the
audit ledger, replay historical decisions, and generate signed
compliance dossiers that can be verified offline by external
auditors.

## What's pre-loaded

The container boots with the **financial-services demo seed**:

- **1 workflow** — *Loan Approval Workflow* (sector: financial-services)
- **1 agent** — `loan-officer-agent-001` (SPIFFE-identified)
- **4 tools** — `read_account_balance`, `lookup_customer`, `transfer_funds`, `submit_payment`
- **3 historical decisions** across the risk spectrum:
  - **ALLOW** (low risk) — customer lookup, no triad review needed
  - **ALLOW** (medium risk) — USD 12,500 vendor transfer, escalated to triad → MAJORITY consensus
  - **DENY** (critical risk) — USD 95,000 to unverified beneficiary, fails policy
- **1 pre-signed Ed25519 dossier** for the medium-risk decision — verifies offline

## Try it

The interactive Swagger UI is at **[`/docs`](/docs)** — every endpoint has a *Try it out* button.

Key flows to explore:

1. **`GET /v1/control/workflows`** — see the seeded workflow with its agent count.
2. **`GET /v1/control/audit`** — pass `workflow_id`, `from`, and `to` (ISO-8601 UTC); the seeded entries are at `2026-05-10T09:15Z`, `11:42Z`, and `14:03Z`.
3. **`POST /v1/control/replay`** — pass an `audit_id` from step 2; get back the full reconstructed decision context including triad verdicts and commitments.
4. **`POST /v1/control/dossier`** — generate a fresh signed dossier for any audit_id.
5. **`GET /v1/control/dossier/{id}`** — fetch the signed dossier. The `signature_hex` and `public_key_hex` fields verify the manifest with any standard Ed25519 verifier — Verixa is not in the trust path.

## Architecture

The container ships **Phase-0 in-memory implementations** of every
collaborator (registries, audit ledger, replay vault, dossier store).
The Protocol-typed interfaces mean Phase-1 swaps the backing
implementations (Postgres, MinIO, HashiCorp Vault) without changing
the API surface or the HTTP routes.

Components live in this image:

- **Runtime gateway** — request validation, structured logging,
  Ed25519 audit ledger
- **Tool firewall** — allow-list + argument-bounds checks
- **Policy engine** — OPA + 4 Rego policies + signed bundles
- **Risk engine** — scores decisions, routes high-risk to triad
- **Triad review engine** — 3 independent LLM reviewers with
  commit-reveal protocol (live-tested against AMD MI300X)
- **Replay vault** — content-addressable encrypted bundles
  (AES-256-GCM); GDPR Article 17 cryptographic erasure
- **Compliance dossier generator** — Ed25519-signed evidence packs
  matching the EU AI Act Annex IV shape

## Cryptography

Every audit record is hash-chained (SHA-256) and signed (Ed25519).
Replay bundles are sealed with per-tenant AES-256-GCM keys.
Dossiers are signed manifests over canonical-JSON; verification
needs **only** the JSON, the signature, and the public key —
no live call back to Verixa.

## Tests

The full system has **1050 unit tests with 100% line + branch
coverage**. 7 additional tests are gated behind Docker (1 Redis,
2 MinIO, 4 live AMD MI300X). The triad reviewer protocol has been
live-tested against Qwen3-0.6B served via vLLM-on-ROCm on a
real MI300X droplet.

## License

MIT.

## Source

[github.com/v-sen/verixa](https://github.com/v-sen/verixa) (this is the Phase-0 hackathon submission for the AMD Developer Cloud × lablab.ai hackathon, Track 1: AI Agents.)
