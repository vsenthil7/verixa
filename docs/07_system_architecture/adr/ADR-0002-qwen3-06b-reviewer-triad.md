# ADR-0002 — Reviewer triad: Qwen3-0.6B × 3 with distinct system prompts

- **Status:** Accepted
- **Date:** 2026-04-18
- **Phase:** 0 (hackathon prototype)
- **Decision owner:** v_sen
- **Affects:** Triad Review Engine (`apps/runtime/verixa_runtime/triad/`), MI300X deployment

## Context

The Verixa architecture calls for a **triad of independent AI reviewers** to verify high-risk actions. The production design (Phase 1+) targets *heterogeneous* model families to maximise independence: e.g. Qwen3-72B + Llama-3.3-70B + DeepSeek-V3, deployed across separate GPU instances, each running through a different inference framework where possible (vLLM vs TGI vs SGLang).

For Phase 0 on the AMD Developer Cloud MI300X allocation (single 8-GPU node, ~192 GB HBM total), running three different 70B+ models is **operationally infeasible** in the hackathon window:

- Three checkpoints to download, version, and validate
- Three vLLM (or equivalent) instances to configure
- Three sets of generation parameters to tune
- Memory budget tight even at INT8

The triad design also requires that no reviewer can be biased by another's verdict (see ADR-0003). The **commit-reveal protocol** is the mechanism for that. As long as the protocol holds, the choice of underlying model is a **swappable detail** of the reviewer, not a property of the triad architecture.

A judge or buyer will reasonably ask: *"if all three reviewers are the same model, what does the triad actually buy you?"* This decision must be defensible.

## Decision

For Phase 0, deploy **three instances of Qwen3-0.6B** on the MI300X, each fronted by an OpenAI-compatible vLLM server on a distinct port (8001, 8002, 8003). Each reviewer instance runs with a **distinct system prompt** encoding a different review persona:

1. **Conservative reviewer** — biased toward escalation; weighs regulatory risk heavily; lower threshold for "needs human review"
2. **Pragmatic reviewer** — biased toward "is this actually how a competent practitioner would handle this"; weighs operational cost
3. **Sceptical reviewer** — actively looks for adversarial framing, missing context, or rationalisations in the action being reviewed

The protocol (commit-reveal, hash-commit-before-reveal, majority + supermajority consensus) treats the three reviewers as **opaque verdict-producers**. The model choice and persona prompts are configuration, not architecture.

Concrete files:

- `apps/runtime/verixa_runtime/triad/reviewer.py` — Reviewer class; protocol-typed, accepts any HTTP endpoint that speaks the OpenAI Chat Completions API
- `apps/runtime/verixa_runtime/triad/prompts.py` — the three system prompts (conservative / pragmatic / sceptical)
- `apps/runtime/verixa_runtime/triad/orchestrator.py` — runs all three in parallel; collects commits then reveals
- Deployment: live MI300X at `http://165.245.133.120:8000` runs all three vLLM servers (gated integration tests in `test_triad_integration.py`)

## Consequences

### Positive

- **Phase 0 runs in budget.** Three Qwen3-0.6B fit comfortably in the MI300X allocation with room for batch concurrency.
- **The triad protocol is exercised end-to-end with a real LLM** — commit-reveal works, consensus computation works, dissent is detected and recorded.
- **Model swap is configuration-only.** `triad/reviewer.py` accepts any OpenAI-compatible endpoint; Phase 1's heterogeneous swap is a YAML change, not a code change.
- **The system-prompt-persona experiment is interesting in its own right** — three same-model reviewers with different prompts produce **measurably different verdicts** on borderline cases (verified by `test_triad_integration.py::test_three_personas_disagree_on_borderline`). This is itself a finding worth surfacing in the demo.

### Negative

- **Three same-model reviewers are correlated.** They share training-data biases, instruction-tuning biases, and tokeniser-level failure modes. The "independence" claim is **weak** in Phase 0 and we must say so explicitly.
- **A judge may discount the triad's value** if not given the Phase-1 swap context up front. Mitigation: README + USE_CASES + this ADR all make the Phase 0 vs Phase 1 distinction explicit.
- **The hackathon demo's "Annex IV-aligned audit trail" claim is weaker** with same-model reviewers than with heterogeneous reviewers. We use hardened language ("Annex IV-aligned" not "regulator-ready"; "evidence supports demonstrating" not "proves") to keep claims defensible.

### Mitigations

- README explicitly corrects an earlier draft that listed reviewers as "Qwen3-72B + Llama-3.3-70B + DeepSeek-V3" — the corrected row reads "Qwen3-0.6B × 3 with distinct system prompts (conservative/pragmatic/sceptical) — protocol is model-agnostic; Phase 1 swaps for heterogeneous family".
- The triad protocol's commit-reveal mechanism is **model-independent**; it works whether reviewers are different sizes of the same model, different families, or even different vendors. The architecture is what's being audited, not the specific weights.
- Phase 1 ADRs will document the heterogeneous-model rollout and validate the "independence" claim with measured disagreement rates across families.

## Alternatives considered

1. **One Qwen3-72B reviewer instead of three Qwen3-0.6B** — rejected. Loses the entire triad protocol; reduces Verixa to a single-LLM rubber stamp.
2. **Three Qwen3-0.6B with identical prompts** — rejected. Three identical reviewers give correlated verdicts almost by definition; the persona-prompt variation is the minimum interesting variation we can introduce within the same model.
3. **Mixing Qwen3-0.6B with Phi-3-mini and Gemma-2B (all small)** — considered. Rejected for Phase 0 because each new model family adds vLLM configuration overhead and increases the chance of one reviewer failing during a live demo. Filed as Phase-1 ADR-0006-stretch candidate.
4. **Synthetic / mocked reviewers** — rejected for the demo path. We do have mocked reviewers for unit tests (so the test suite doesn't depend on live LLMs), but the live demo path uses real models.

## Verification

- `apps/runtime/tests/test_triad_protocol.py` proves the commit-reveal mechanism doesn't depend on reviewer identity
- `apps/runtime/tests/test_triad_orchestrator.py` proves the consensus computation works with any 3 verdicts
- Gated `packages/verixa-python/tests/test_triad_integration.py` (4 tests) runs against the live MI300X triad and asserts protocol invariants — never specific verdicts (verdicts will vary; the protocol must not)
- Demo seed (CP-16) includes decision B which is a triad-MAJORITY case; replay shows three distinct verdicts + commitments

## Related

- BRD: BR-02 (independent triad review)
- Use case: UC-02 (medium-risk transfer with triad consensus)
- Companion ADRs: ADR-0003 (commit-reveal protocol)
- Will be revisited in Phase 1: ADR-0011 (heterogeneous reviewer rollout, placeholder)
