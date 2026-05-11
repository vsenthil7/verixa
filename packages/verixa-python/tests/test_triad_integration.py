"""Live MI300X integration test for the triad orchestrator (CP-10.4).

Opt-in via the ``integration`` pytest marker; the default pytest run
uses ``-m 'not integration'`` so this suite stays out of the
fast-feedback loop.

The test gate probes the droplet at module load and skips cleanly if
unreachable (so a developer running ``pytest -m integration`` on a
laptop without VPN access doesn't see red).

Live LLM output is non-deterministic; we therefore assert the
**protocol invariants** rather than specific decisions:

  - All three reviewers produced a verdict (even if one synthesised
    via outage path).
  - Three commitments were generated; sha256_hex format valid.
  - The reveal-then-verify step inside compute_consensus succeeded
    (consensus.kind is NEVER INTEGRITY_FAILURE for live
    OpenAICompatReviewer calls -- those nonces and hashes are
    computed in-process by the orchestrator, not over the wire,
    so the only way to fail is if the protocol code itself is
    broken).
  - consensus.kind is one of {UNANIMOUS, MAJORITY, SPLIT}.
  - consensus_to_decision returns a VerdictDecision.

Phase-0 deviation note: the page-1 brief specifies three distinct
reviewer models (Qwen3-72B + Llama-3.3-70B + DeepSeek-V3). The
droplet currently serves Qwen3-0.6B only, so all three slots share
the same backing model with different system prompts. The protocol
surface is identical; swapping in three distinct larger models is a
config change only.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from verixa_runtime.triad import (
    ConsensusKind,
    OpenAICompatReviewer,
    ReviewerConfig,
    ReviewerId,
    TriadOrchestrator,
    VerdictDecision,
    consensus_to_decision,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Module-level droplet probe -- skip cleanly if unreachable
# ---------------------------------------------------------------------------


_DROPLET_BASE_URL = "http://165.245.133.120:8000"
_DROPLET_MODEL = "Qwen/Qwen3-0.6B"
_DROPLET_PROBE_TIMEOUT = 5.0


def _droplet_is_up() -> bool:
    """Return True iff the droplet's /v1/models endpoint responds 200."""
    try:
        with httpx.Client(timeout=_DROPLET_PROBE_TIMEOUT) as c:
            r = c.get(f"{_DROPLET_BASE_URL}/v1/models")
        return r.status_code == 200
    except httpx.HTTPError:
        return False


if not _droplet_is_up():  # pragma: no cover -- guard depends on droplet
    pytest.skip(
        f"MI300X droplet at {_DROPLET_BASE_URL} unreachable; "
        f"skipping live triad integration tests",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Three distinct system prompts -- Phase-0 deviation: same backing
# model, three "personalities" to give each reviewer slot an
# independent vantage on the action. Production replaces this with
# three distinct models.
# ---------------------------------------------------------------------------


_PROMPT_CONSERVATIVE = (
    "You are a conservative compliance reviewer for an AI governance "
    "system. Default to escalating any action involving money, "
    "external communication, or irreversible operations. Be strict."
)

_PROMPT_PRAGMATIC = (
    "You are a pragmatic operations reviewer for an AI governance "
    "system. Allow routine read-only actions; escalate unusual or "
    "high-value actions. Balance throughput with safety."
)

_PROMPT_SCEPTICAL = (
    "You are a sceptical security reviewer for an AI governance "
    "system. Deny any action that could exfiltrate data or modify "
    "production state. Assume adversarial intent unless clear."
)


def _build_live_triad() -> TriadOrchestrator:
    return TriadOrchestrator(
        reviewer_a=OpenAICompatReviewer(
            config=ReviewerConfig(
                base_url=_DROPLET_BASE_URL,
                model=_DROPLET_MODEL,
                reviewer_id=ReviewerId.REVIEWER_A,
                system_prompt=_PROMPT_CONSERVATIVE,
                temperature=0.0,
                timeout_seconds=60.0,
            )
        ),
        reviewer_b=OpenAICompatReviewer(
            config=ReviewerConfig(
                base_url=_DROPLET_BASE_URL,
                model=_DROPLET_MODEL,
                reviewer_id=ReviewerId.REVIEWER_B,
                system_prompt=_PROMPT_PRAGMATIC,
                temperature=0.0,
                timeout_seconds=60.0,
            )
        ),
        reviewer_c=OpenAICompatReviewer(
            config=ReviewerConfig(
                base_url=_DROPLET_BASE_URL,
                model=_DROPLET_MODEL,
                reviewer_id=ReviewerId.REVIEWER_C,
                system_prompt=_PROMPT_SCEPTICAL,
                temperature=0.0,
                timeout_seconds=60.0,
            )
        ),
    )


# ---------------------------------------------------------------------------
# Tests -- protocol invariants only (live LLM output is non-deterministic)
# ---------------------------------------------------------------------------


async def test_live_triad_run_produces_three_verdicts() -> None:
    """Run the full protocol once; assert structural invariants."""
    triad = _build_live_triad()
    audit_id = uuid.uuid4()
    summary = (
        "action.type=tool_call tool_name=transfer_funds "
        "role=loan-officer workflow_id=test-wf-001"
    )
    outcome = await triad.run(
        audit_id=audit_id,
        governed_action_summary=summary,
    )
    # Exactly three verdicts in slot order.
    assert len(outcome.verdicts) == 3
    assert outcome.verdicts[0].reviewer_id == ReviewerId.REVIEWER_A
    assert outcome.verdicts[1].reviewer_id == ReviewerId.REVIEWER_B
    assert outcome.verdicts[2].reviewer_id == ReviewerId.REVIEWER_C
    # All three carry the same audit_id (binding to the governed action).
    for v in outcome.verdicts:
        assert v.audit_id == audit_id
    # Exactly three commitments, format valid (Commitment.__post_init__
    # would have raised at construction time if not).
    assert len(outcome.commitments) == 3
    for c in outcome.commitments:
        assert len(c.sha256_hex) == 64


async def test_live_triad_commit_reveal_binds_in_process() -> None:
    """The commit-reveal step happens entirely in the orchestrator
    process; commitments and nonces never leave the box, so
    INTEGRITY_FAILURE is impossible for a correctly-implemented
    protocol. Confirm that here -- if this ever fires, the protocol
    code has a bug, not the droplet."""
    triad = _build_live_triad()
    outcome = await triad.run(
        audit_id=uuid.uuid4(),
        governed_action_summary=(
            "action.type=tool_call tool_name=read_account_balance "
            "role=customer-service workflow_id=test-wf-002"
        ),
    )
    assert outcome.consensus.kind != ConsensusKind.INTEGRITY_FAILURE


async def test_live_triad_consensus_classifies_into_known_kind() -> None:
    """consensus.kind must be one of the four enum values; the gateway
    helper translates it to a VerdictDecision without raising."""
    triad = _build_live_triad()
    outcome = await triad.run(
        audit_id=uuid.uuid4(),
        governed_action_summary=(
            "action.type=tool_call tool_name=lookup_customer "
            "role=customer-service workflow_id=test-wf-003"
        ),
    )
    assert outcome.consensus.kind in (
        ConsensusKind.UNANIMOUS,
        ConsensusKind.MAJORITY,
        ConsensusKind.SPLIT,
    )
    # consensus_to_decision must accept any of the three above without
    # raising; the result is a valid VerdictDecision enum member.
    final = consensus_to_decision(outcome)
    assert final in (
        VerdictDecision.ALLOW,
        VerdictDecision.DENY,
        VerdictDecision.ESCALATE,
    )


async def test_live_triad_audit_emit_hook_receives_commitments_before_reveal() -> None:
    """The integrity anchor: audit_emit fires AFTER commit + BEFORE
    reveal. We can't observe reveal directly (it's pure-function), but
    we can verify the hook receives exactly the same commitments that
    end up in the final outcome -- proving nothing changed between
    the two phases."""
    captured: dict[str, object] = {}

    async def emit_hook(audit_id: uuid.UUID, commitments: list) -> None:
        captured["audit_id"] = audit_id
        captured["commitments"] = list(commitments)

    triad = _build_live_triad()
    audit_id = uuid.uuid4()
    outcome = await triad.run(
        audit_id=audit_id,
        governed_action_summary=(
            "action.type=tool_call tool_name=submit_payment "
            "role=loan-officer workflow_id=test-wf-004"
        ),
        audit_emit=emit_hook,
    )
    assert captured["audit_id"] == audit_id
    assert len(captured["commitments"]) == 3  # type: ignore[arg-type]
    assert tuple(captured["commitments"]) == outcome.commitments  # type: ignore[arg-type]
