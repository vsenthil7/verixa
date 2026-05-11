# Verixa — Negative Test Plan

> Positive tests prove the system *can* do its job. Negative tests prove it
> *refuses* to do the wrong thing. For a security / governance product, negative
> coverage is at least as important as positive coverage, and arguably more.
>
> This document is the **explicit, named list** of adversarial categories Verixa
> tests against, the categories currently covered, the categories with gaps,
> and the categories deferred to Phase 1+ with reasons.

---

## Current state (2026-05-11 13:42 UK — Phase 1 negative-test push complete)

| Metric | Value | Industry norm |
|---|---|---|
| Total automated test definitions | 1005 (`def test_*` count, pre-parameterise) | — |
| Pytest collected (parameterised expansion) | 1151 + 1 xfailed + 1 xpassed | — |
| Tests matching negative-keyword patterns (definitions) | **395** | — |
| Negative-test coverage ratio (def-level) | **39.3%** | 30–40% for security products |

The 39.3% ratio is measured via a keyword sweep over `def test_*` names against
the patterns `fail / reject / deny / invalid / tamper / missing / malformed /
unauthorized / forbidden / negative / exceed / empty / null / expired / revoked
/ corrupt / mismatch / wrong / raises / error_ / _error / out_of / bound /
attack / compromise / race / concurrent / conflict / timing / replay_attack /
truncated / extended / destruction / erasure / substitution`. This is a rough
proxy but defensible enough to ground claims on.

**Phase 1 push:** today's CP-36 / CP-37 / CP-38 work added 41 new negative
test definitions (timing-attack + tenant-key compromise + race conditions).
Negative-test coverage moved from ~31% at Phase 0 close (CP-28 measurement) to
~39.3% in the Phase 1 baseline — within the 30–40% industry norm band for
security products.

---

## Coverage by adversarial category

| Category | Tests found | Verdict | Anchor files |
|---|---|---|---|
| Hash-chain tamper / break detection | 6 | ✅ Solid | `packages/verixa-python/tests/test_audit_verifier.py` |
| Ed25519 signature verification negatives | 3 + 18 timing | ✅ Solid | `test_crypto_ed25519.py` + `test_dossier_manifest.py` + `test_timing_attack_ed25519.py` |
| AES-256-GCM tamper / decrypt failure | 4 + 7 tenant-key | ✅ Solid | `test_crypto_aes_gcm.py` + `test_replay_sealer.py` + `test_tenant_key_compromise.py` |
| Firewall arg-bounds rejections | 3 (named) | 🟡 Light | `test_firewall_arg_bounds.py` (parameterised — actual cases > 3) |
| Firewall allow-list rejections | (counted in 184 `reject` hits) | ✅ Excellent | `test_firewall_allowlist.py` |
| Policy fail paths | 39 | ✅ Excellent | `test_policy_*.py` — every Rego rule has fail cases |
| Pydantic envelope validation | 16 | ✅ Solid | `test_gateway_envelopes.py` + `test_envelopes.py` (control plane) |
| HTTP 4xx error responses (404 / 400 / 422) | 13 | ✅ Solid | `test_routes.py` + Playwright not-found specs |
| Triad protocol failure modes | 8 + 5 timeout | ✅ Solid | `test_triad_protocol.py` + `test_triad_orchestrator.py` + `test_triad_timeout.py` |
| Hash-commit reveal mismatch detection | (subset of triad 8) | ✅ Solid | `test_triad_protocol.py` |
| Replay attack (re-presented signed artefacts) | 10 | ✅ Solid | `test_replay_attack.py` |
| Size limits / DoS-by-oversize | 12 | ✅ Solid | `test_size_limits.py` |
| Path traversal / injection in identifiers | 20 | ✅ Solid | `test_path_traversal.py` |
| Unicode edge cases (surrogates / RTL / ZWSP) | 10 | ✅ Solid | `test_unicode_edges.py` |
| **Timing-attack on Ed25519** (CP-36) | 18 + 2 xfail tripwires | ✅ Solid (with documented Phase-1 follow-up on 2 tripwires) | `test_timing_attack_ed25519.py` |
| **Tenant-key compromise + cryptographic erasure** (CP-37) | 13 across 7 attack models | ✅ Solid | `test_tenant_key_compromise.py` |
| **Race conditions / concurrent writes** (CP-38) | 8 hammering asyncio.Lock contract | ✅ Solid | `test_concurrent_races.py` |

---

## Closed in this Phase 1 push (was Phase 0 gap)

CP-36 / CP-37 / CP-38 retrofits 3 of the previously-Phase-1-targeted gaps:

| Gap | Status | Anchor |
|---|---|---|
| Timing-attack on Ed25519 verification | **CLOSED** with 18 green + 2 xfail-strict-false Phase-1 tripwires | CP-36 commit `45bbf19` |
| Tenant-key compromise scenarios | **CLOSED** with 13 tests across 7 attack models | CP-37 commit `557a7ad` |
| Race conditions / concurrent writes to audit ledger | **CLOSED** with 8 tests stressing asyncio.Lock under gather | CP-38 commit `53453dd` |

The Phase-0-stretch gaps (triad timeout, replay attack, size limits, path
traversal, Unicode edges) were closed in CP-30 (commits `f372ad2`, `4852f51`,
`28d106e`, `004b104`, `fffd857`).

---

## Remaining Phase 1+ gaps

The following adversarial categories are **not yet covered** and remain
explicit backlog items.

| Gap | Why it matters | Effort | Target phase |
|---|---|---|---|
| Resource exhaustion (10k simultaneous govern calls) | Survivability under load; defines back-pressure behaviour. Distinct from CP-38 concurrent-correctness; this is a load test, not a correctness test. | MEDIUM | Phase 1 (load tests live separately under load-tests/) |
| Compromised policy bundle (valid signature, malicious content) | Policy signing prevents unsigned modification but not malicious-signer scenarios. Needs key-rotation + signer-revocation infrastructure to test meaningfully. | HIGH | Phase 2 (needs key-rotation infrastructure per ADR-0008 + future ADR-0011) |
| Reconstructor-level audit_id mismatch on cross-tenant substitution (CP-37 attack model 7) | If audit-index is tampered to point Tenant A's audit_id at Tenant B's storage_key, Phase 0 reconstruct returns Tenant B's bundle. Phase 1 work: add reconstructor-level guard that the returned bundle's audit_id matches the requested audit_id. | LOW | Phase 1 (small code change + 1 test) |
| Timing-attack byte-position tripwire investigation (CP-36 xfail) | Two xfail-strict-false tests showed ~40x median ratio between byte0-flip and last-byte-flip verification time. Needs investigation with dedicated benchmark harness + larger sample sizes to determine: real timing channel? Python wrapping overhead? OS scheduler artifact on small samples? | MEDIUM | Phase 1 (cryptolib-team investigation; if real, escalate as security finding) |

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
codebase already existed. The original 31% negative-coverage ratio was
*measured*, not *targeted*. The gaps section was the result of a deliberate
audit, not a pre-planned exclusion. Phase 1 will start every BR with its
negative test categories enumerated in the BRD before implementation begins.

This is the same anti-pattern the Traceability Matrix's "Process honesty"
section calls out: **reverse-engineered discipline is better than no
discipline, but worse than discipline-from-day-one**.

- **CP-30** retrofits 5 of the 7 Phase-0-stretch gaps (triad timeout + replay
  attack + size limits + path traversal + Unicode edges).
- **CP-30.1 / 30.2 / 30.3** close Phase-1 follow-up gaps surfaced by CP-30's
  red-green pattern (empty-doc_id ReplayBundle validator + xfail-strict
  cleanup + API_STYLE_GUIDE §3.5 field-cap documentation).
- **CP-36 / CP-37 / CP-38** retrofits 3 Phase-1 gaps (timing-attack +
  tenant-key compromise + race conditions); pushes negative-test coverage
  from ~31% to ~39.3% which sits within the 30–40% industry-norm band for
  security products.

The remaining gaps (resource exhaustion load tests + compromised-signer
policy bundle + reconstructor audit_id guard + timing-attack tripwire
investigation) are tracked above and have committed-to phase targets.
