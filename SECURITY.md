# Security Policy

Verixa is an AI runtime governance platform. Security issues affect not just
this repo but every audit trail it produces. Please report responsibly.

## Supported versions

| Version | Phase | Supported |
|---|---|---|
| `main` (Phase 0 prototype) | Hackathon | ✅ Active development; security issues triaged |
| Tagged releases | (none yet) | — |

Phase 1 will introduce semver releases and a formal support window.

## Reporting a vulnerability

**Please do NOT open a public GitHub issue for security-sensitive findings.**

Email: `security@verixa.example` *(placeholder until Phase 1 — currently
report via private GitHub Security Advisory at
https://github.com/v-sen/verixa/security/advisories/new)*

When reporting, please include:

- A clear description of the issue and its impact
- Steps to reproduce (or a proof-of-concept)
- Affected versions / commits
- Your suggested fix, if any
- Whether you'd like to be credited in the advisory (and how)

We aim to:

- Acknowledge receipt within **72 hours**
- Provide an initial assessment within **7 days**
- Publish a fix and advisory within **30 days** for high/critical issues
- Publish a fix and advisory within **90 days** for medium/low issues

## Scope

In scope:

- `apps/runtime/` (governance runtime)
- `apps/control-plane-api/` (operator API)
- `apps/control-plane-ui/` (operator UI)
- `packages/verixa-python/` (core library)
- `tools/audit_verify.py` (offline verifier)
- `deploy/huggingface/` (deploy assets)

Out of scope (report upstream):

- Vulnerabilities in dependencies (report to the dependency maintainer)
- Issues in the Hugging Face Spaces infrastructure (report to HF)
- Issues in the AMD MI300X cluster (report to AMD Developer Cloud)

## Cryptographic notes

Verixa uses standard primitives (Ed25519, AES-256-GCM, SHA-256) via `pynacl`
and `cryptography`. **No custom cryptography is implemented.** If you find a
weakness in how Verixa *uses* these primitives, please report it. Weaknesses
in the primitives themselves should be reported to those library maintainers.

## Acknowledgements

Researchers who report verified issues will be credited in the relevant
advisory (with their consent) and in `CHANGELOG.md`.
