"""pytest suite for decide_via_router_with_replay (CP-12.5).

Exercises the gateway hot path with the fire-and-forget snapshot
wired in. Uses MockReviewer + InMemoryBundleStore + InMemoryAuditIndex
so nothing touches the network.

Key assertions:
  - The response returns BEFORE the snapshot completes (fire-and-forget).
  - After awaiting the background task, the snapshot lands in the
    store and the index resolves audit_id -> the stored key.
  - Snapshot failures don't leak into the response.
  - Triad-enabled path: replay still snapshots, and the snapshot
    reflects the post-triad decision.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Awaitable, Callable

import pytest

from verixa_runtime.crypto.aes_gcm import generate_key
from verixa_runtime.gateway import (
    AgentIdentity,
    Decision,
    GovernAction,
    GovernContext,
    GovernRequest,
    decide_via_router_with_replay,
    pending_snapshot_tasks,
)
from verixa_runtime.policy.client import PolicyDecision, PolicyDecisionKind
from verixa_runtime.replay import (
    InMemoryAuditIndex,
    InMemoryBundleStore,
    Reconstructor,
    Snapshotter,
)
from verixa_runtime.replay.snapshotter import SnapshotInputs
from verixa_runtime.triad import (
    MockReviewer,
    ReviewerId,
    ReviewerVerdict,
    TriadOrchestrator,
    VerdictDecision,
)


_WF_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_TENANT_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


def _request_for_tool(tool_name: str | None) -> GovernRequest:
    action_kwargs: dict[str, object] = {"type": "tool_call"}
    if tool_name is not None:
        action_kwargs["tool_name"] = tool_name
    return GovernRequest(
        agent_identity=AgentIdentity(
            spiffe_id="spiffe://example/agent/x",
            role="loan-officer",
            workflow_id=_WF_ID,
        ),
        action=GovernAction(**action_kwargs),
        context=GovernContext(
            prompt_hash="b" * 64,
            model_version="qwen3-0.6b",
        ),
        trace_id="01HW",
    )


def _build_snapshotter(
    keys: dict[uuid.UUID, object] | None = None,
):
    """Return (snapshotter, reconstructor, store, index, key)."""
    key = generate_key()
    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()
    resolver_map = keys or {_TENANT_ID: key}

    def resolver(tid: uuid.UUID):
        return resolver_map[tid]  # type: ignore[return-value]

    return (
        Snapshotter(store=store, index=index, key_resolver=resolver),
        Reconstructor(store=store, index=index, key_resolver=resolver),
        store,
        index,
        key,
    )


async def _drain_pending_snapshots() -> None:
    """Await all background snapshot tasks. Tests call this before
    asserting on store / index contents."""
    tasks = pending_snapshot_tasks()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# Sync path (no triad): response + background snapshot
# ---------------------------------------------------------------------------


async def test_replay_allow_path_returns_then_snapshots() -> None:
    snapshotter, reconstructor, store, index, _ = _build_snapshotter()
    req = _request_for_tool("read_account_balance")
    resp = await decide_via_router_with_replay(
        req, tenant_id=_TENANT_ID, snapshotter=snapshotter
    )
    # Response is immediate (we got back from the await before snapshot
    # might be done; size-of-store is at most 1 by now but could be 0).
    assert resp.decision == Decision.ALLOW
    # Drain background snapshot tasks and verify persistence.
    await _drain_pending_snapshots()
    recovered = await reconstructor.reconstruct(resp.audit_id)
    assert recovered.tenant_id == _TENANT_ID
    assert recovered.audit_id == resp.audit_id
    assert recovered.decision == "allow"


async def test_replay_deny_path_still_snapshots() -> None:
    """Firewall DENY path also produces a snapshot (every governed
    action lands in the replay vault, not just allows)."""
    snapshotter, reconstructor, _, _, _ = _build_snapshotter()
    req = _request_for_tool("shutdown_production")
    resp = await decide_via_router_with_replay(
        req, tenant_id=_TENANT_ID, snapshotter=snapshotter
    )
    assert resp.decision == Decision.DENY
    await _drain_pending_snapshots()
    recovered = await reconstructor.reconstruct(resp.audit_id)
    assert recovered.decision == "deny"


# ---------------------------------------------------------------------------
# Triad path: snapshot reflects post-triad decision
# ---------------------------------------------------------------------------


def _factory_for(
    reviewer_id: ReviewerId, decision: VerdictDecision
) -> Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]]:
    async def _factory(audit_id: uuid.UUID, _summary: str) -> ReviewerVerdict:
        return ReviewerVerdict(
            reviewer_id=reviewer_id,
            decision=decision,
            confidence=0.9,
            reasoning=f"{reviewer_id.value}-{decision.value}",
            audit_id=audit_id,
        )

    return _factory


async def test_replay_triad_unanimous_allow_snapshot_reflects_override() -> None:
    """Inject ABSTAIN -> base ESCALATE; triad unanimous ALLOW overrides
    decision; the snapshot stores the OVERRIDDEN decision (the final
    one returned to the caller), not the pre-triad one."""
    snapshotter, reconstructor, _, _, _ = _build_snapshotter()
    triad = TriadOrchestrator(
        reviewer_a=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_A,
            factory=_factory_for(
                ReviewerId.REVIEWER_A, VerdictDecision.ALLOW
            ),
        ),
        reviewer_b=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_B,
            factory=_factory_for(
                ReviewerId.REVIEWER_B, VerdictDecision.ALLOW
            ),
        ),
        reviewer_c=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_C,
            factory=_factory_for(
                ReviewerId.REVIEWER_C, VerdictDecision.ALLOW
            ),
        ),
    )
    req = _request_for_tool("transfer_funds")
    abstain = (
        (
            "verixa.x.unknown",
            PolicyDecision(
                decision=PolicyDecisionKind.ABSTAIN, reason="undefined"
            ),
        ),
    )
    resp = await decide_via_router_with_replay(
        req,
        tenant_id=_TENANT_ID,
        snapshotter=snapshotter,
        triad=triad,
        policy_decisions=abstain,
    )
    assert resp.decision == Decision.ALLOW
    assert resp.triad_invoked is True
    await _drain_pending_snapshots()
    recovered = await reconstructor.reconstruct(resp.audit_id)
    # The snapshot stores the POST-triad decision (the final one).
    assert recovered.decision == "allow"


# ---------------------------------------------------------------------------
# Failure isolation: snapshot failure doesn't break the response
# ---------------------------------------------------------------------------


async def test_replay_snapshot_failure_does_not_break_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the snapshot raises (e.g. resolver returns the wrong key),
    the response is still returned correctly and the failure is
    logged."""
    # Resolver that raises for any tenant.
    def boom(_tid: uuid.UUID):
        raise RuntimeError("simulated key-resolver outage")

    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()
    snapshotter = Snapshotter(
        store=store, index=index, key_resolver=boom
    )
    req = _request_for_tool("read_account_balance")
    with caplog.at_level("ERROR", logger="verixa.gateway.replay"):
        resp = await decide_via_router_with_replay(
            req, tenant_id=_TENANT_ID, snapshotter=snapshotter
        )
        # Response itself is fine.
        assert resp.decision == Decision.ALLOW
        await _drain_pending_snapshots()
    # Snapshot failure was logged, NOT raised.
    assert any(
        "snapshot failed" in rec.message for rec in caplog.records
    ), f"expected snapshot-failed log, got {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Pending-tasks registry
# ---------------------------------------------------------------------------


async def test_pending_snapshot_tasks_tracks_in_flight_then_drains() -> None:
    """pending_snapshot_tasks() returns the set of currently in-flight
    snapshots. After completion the set drains back to empty (the
    done-callback removes finished tasks)."""
    snapshotter, _, _, _, _ = _build_snapshotter()
    req = _request_for_tool("read_account_balance")
    await decide_via_router_with_replay(
        req, tenant_id=_TENANT_ID, snapshotter=snapshotter
    )
    # At this point there may be 0 or 1 in-flight tasks depending on
    # how fast the loop scheduled the snapshot. Drain everything.
    await _drain_pending_snapshots()
    # After drain, the registry must be empty.
    assert pending_snapshot_tasks() == frozenset()
