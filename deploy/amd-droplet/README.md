# AMD MI300X Droplet — Verixa Triad Reviewer Deployment

This directory contains the AMD Developer Cloud / MI300X side of Verixa.
It is **separate from `deploy/docker-compose/`** which is the local dev
stack (Postgres, Redis, OPA, Vault, MinIO, Prometheus).

## Why two compose contexts?

| Context | Where it runs | What it serves |
|---|---|---|
| `deploy/docker-compose/` | Local developer machine (Windows/macOS/Linux) | Postgres, Redis, OPA, Vault dev, MinIO, Prometheus — the support services for the Verixa Runtime Gateway and Control Plane API |
| `deploy/amd-droplet/` | AMD Developer Cloud MI300X droplet | `vllm/vllm-openai-rocm:latest` serving the reviewer triad (Qwen3 / Llama-3.3 / DeepSeek-V3) at an OpenAI-compatible endpoint |

Verixa Runtime Gateway runs locally and **calls into** the remote MI300X
inference endpoint over HTTPS. The two are independent.

## Validated baseline (2026-05-10)

Source: `AMD_test/verixa-build-testing-memory.md`, run logs at
`AMD_test/workspace/run_log/run_log2026-05-10-09-30.txt` and `09-47.txt`.

- **Host:** `rocm-7-2-software-gpu-mi300x1-192gb-devcloud-atl1`
- **OS:** Ubuntu 24
- **Python:** 3.12.3 at `/usr/bin/python3` (no `python` symlink — use
  `python3` or set `alias python=python3` in `.bashrc`)
- **Pip:** 24.0
- **System packages already present** (per droplet baseline; do NOT reinstall):
  `amdsmi`, `boto3`, `cryptography`, `Jinja2`, `jsonschema`, `Pygments`,
  `PyJWT`, `PyYAML`, `requests`, `rich`, `urllib3`, plus standard cloud-init /
  Ubuntu Pro tooling.
- **Validated serving stack:** `vllm/vllm-openai-rocm:latest` Docker image
- **Validated device flags:** `/dev/kfd`, `/dev/dri`, `--group-add=video`,
  `--ipc=host`
- **Validated endpoints:** `GET /v1/models`, `POST /v1/chat/completions`
- **Test model:** `Qwen/Qwen3-0.6B` (small; not the production triad)

## Contents (filled in CP-10 + CP-18)

```
deploy/amd-droplet/
├── README.md                      <- this file
├── run-vllm-rocm.sh               <- (CP-18) launches vLLM container with
│                                    correct ROCm device flags and chosen
│                                    reviewer model
├── triad-launch.sh                <- (CP-18) launches three vLLM containers
│                                    on different ports for the full triad
├── verify-endpoints.sh            <- (CP-10) smoke-tests /v1/models +
│                                    /v1/chat/completions on each reviewer
└── client-baseline.txt            <- pinned droplet pip baseline (audit trail)
```

## Deployment topology options for the triad

Per `plan_audit/AT-Hack0017-003_PLAN_v1_AMENDMENT_*.md` §2.1, three options
are open for the production triad on a single MI300X:

- **Option A:** three vLLM containers on one MI300X with INT8 quantisation
- **Option B:** one MI300X per model (three droplets)
- **Option C:** smaller production-quality models (Qwen3-32B + Llama-3.1-70B + DeepSeek-V2.5)

Decision deferred to CP-10 implementation. Code is parameterised over
`(reviewer_id, endpoint_url, model_name)` triples per
`config/reviewers.yaml.example` so all three options are supported.

## Hackathon fallback

If the locked 70B-class triad won't co-reside even at INT8, demo can run
with **the current Qwen3-0.6B endpoint replicated 3× on different ports**
(reviewers A/B/C all serve from Qwen3-0.6B with different system prompts /
temperatures / seeds to diverge their outputs). This is **honest** — the
README and demo voice-over make clear it's a protocol demonstration; the
production deployment uses the locked triad. The audit ledger and replay
vault don't care about model size.
