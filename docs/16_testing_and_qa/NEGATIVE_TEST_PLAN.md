# Verixa — Negative Test Plan

> Positive tests prove the system *can* do its job. Negative tests prove it
> *refuses* to do the wrong thing. For a security / governance product, negative
> coverage is at least as important as positive coverage, and arguably more.
>
> This document is the **explicit, named list** of adversarial categories Verixa
> tests against, the categories currently covered, the categories with gaps,
> and the categories deferred to Phase 1+ with reasons.

---

## Current state (2026-05-11)

| Metric | Value | Industry norm |
|---|---|---|
| Total automated tests | 1108 (1055 pytest + 35 vitest + 18 Playwright) | — |
| Tests matching negative-keyword patterns | **332** | — |
| Negative-test coverage ratio | **~31%** | 30–40% for security products |

The 31% ratio was measured via a keyword sweep over `def test_*` names against
the patterns `fail / reject / deny / invalid / tamper / missing / malformed /
unauthorized / forbidden / negative / exceed / empty / null / expired / revoked
/ corrupt / mismatch / wrong / raises / error_ / _error / out_of / bound`.
This is a rough proxy but defensible enough to ground claims on.

---

## Coverage by adversarial category

| Category | Tests found | Verdict | Anchor files |
|---|---|---|---|
| Hash-chain tamper / break detection | 6 | ✅ Solid | `packages/verixa-python/tests/test_audit_verifier.py` |
| Ed25519 signature verification negatives | 3 | 🟡 Light | `packages/verixa-python/tests/test_crypto_ed25519.py` + `test_dossier_manifest.py` |
| AES-256-GCM tamper / decrypt failure | 4 | ✅ Solid | `test_crypto_aes_gcm.py` + `test_replay_sealer.py` |
| Firewall arg-bounds rejections | 3 (named) | 🟡 Light | `test_firewall_arg_bounds.py` (parameterised — actual cases > 3) |
| Firewall allow-list rejections | (counted in 184 `reject` hits) | ✅ Excellent | `test_firewall_allowlist.py` |
| Policy fail paths | 39 | ✅ Excellent | `test_policy_*.py` — every Rego rule has fail cases |
| Pydantic envelope validation | 16 | ✅ Solid | `test_gateway_envelopes.py` + `test_envelopes.py` (control plane) |
| HTTP 4xx error responses (404 / 400 / 422) | 13 | ✅ Solid | `test_routes.py` + Playwright not-found specs |
| Triad protocol failure modes | 8 | 🟡 Light | `test_triad_protocol.py` + `test_triad_orchestrator.py` |
| Hash-commit reveal mismatch detection | (subset of triad 8) | ✅ Solid | `test_triad_protocol.py` |

---

## Known gaps (Phase 0 scope)

The following adversarial categories are **not yet covered** and are
acknowledged as Phase 0 documentation gaps. Each row is a future test
backlog item, **not** a hidden bug.

| Gap | Why it matters | Effort | Target phase |
|---|---|---|---|
| Race conditions / concurrent writes to audit ledger | Multiple agents calling `/govern` simultaneously could in theory race the hash-chain emitter | MEDIUM | Phase 0 stretch / Phase 1 |
| Resource exhaustion (10k simultaneous govern calls) | Survivability under load; defines back-pressure behaviour | MEDIUM | Phase 1 (load tests live separately) |
| Triad reviewer timeout (1 of 3 never responds) | Phase 0 happy-path; protocol behaviour on timeout is undefined | LOW | **Phase 0 stretch (this commit, CP-30)** |
| Replay-attack: re-presenting a valid signed dossier | A dossier valid at time T may be re-used adversarially later | MEDIUM | **Phase 0 stretch (CP-30)** |
| Replay bundle size limits (e.g. 1 GB request envelope) | DoS by oversized inputs | LOW | **Phase 0 stretch (CP-30)** |
| Path traversal / injection in tenant ID or workflow name | Phase 0 in-memory mitigates most of this by design; still worth an explicit test | LOW | **Phase 0 stretch (CP-30)** |
| Unicode edge cases in identifiers | Surrogate pairs, RTL marks, zero-width chars in workflow names | LOW | **Phase 0 stretch (CP-30)** |
| Timing-attack on Ed25519 verification | `pynacl` uses constant-time comparisons; assertion test that this is preserved through Verixa's wrapping | MEDIUM | Phase 1 |
| Compromised policy bundle (valid signature, malicious content) | Policy signing prevents unsigned modification but not malicious-signer scenarios | HIGH | Phase 2 (needs key-rotation infrastructure) |
| Tenant-key compromise scenarios | Cryptographic-erasure infrastructure exists; explicit attack scenarios documented but not yet tested | MEDIUM | Phase 1 |

---

## Negative-test discipline going forward

When adding a new business requirement (BR-NN) or use case (UC-NN), the
following negative-test categories MUST be considered and either implemented
or documented as deferred with a reason:

1. **Boundary** — what is the smallest / largest / first / last valid input?
2. **Off-boundary** — what happens one unit outside each boundary?
3. **Malformed** — invalid type, missing required field, extra forbidden field
4. **Tampered** — bit-flipped signature, modified payload after signing
5. **Wrong-identity** — operation attempted with the wrong tenant / agent / role
6. **Resource limit** — input exceeds size / count / time limits
7. **Adversarial input** — Unicode edges, injection patterns, path traversal
8. **Timing** — does behaviour leak information through wall-clock differences?
9. **Replay** — can a valid past artefact be re-used adversarially?
10. **Concurrent** — what happens under parallel access?

The traceability matrix at `../17_traceability_matrix/TRACEABILITY_MATRIX.md`
will be extended in Phase 1 to add a `Negative Tests` column so every BR
row is forced to list its adversarial coverage.

---

## Process honesty

This document was written in **CP-28** (2026-05-11 09:30 UK), after the
codebase already existed. The 31% negative-coverage ratio was *measured*,
not *targeted*. The gaps section above is the result of a deliberate audit,
not a pre-planned exclusion. Phase 1 will start every BR with its negative
test categories enumerated in the BRD before implementation begins.

This is the same anti-pattern the Traceability Matrix's "Process honesty"
section calls out: **reverse-engineered discipline is better than no
discipline, but worse than discipline-from-day-one**. CP-30 retrofits 5 of
the 7 named Phase-0-stretch gaps in the table above.
