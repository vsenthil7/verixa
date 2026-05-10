"""pytest suite for verixa_control_plane.registry (CP-14.4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from verixa_control_plane.envelopes import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    ErrorResponse,
    ToolRegisterRequest,
    ToolRegisterResponse,
    WorkflowListResponse,
    WorkflowRegisterRequest,
    WorkflowRegisterResponse,
)
from verixa_control_plane.registry import (
    InMemoryAgentRegistry,
    InMemoryToolRegistry,
    InMemoryWorkflowRegistry,
    handle_agent_register,
    handle_tool_register,
    handle_workflow_list,
    handle_workflow_register,
)


_NOW = datetime(2026, 5, 11, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Workflow registration + listing
# ---------------------------------------------------------------------------


async def test_workflow_register_success() -> None:
    wf_reg = InMemoryWorkflowRegistry()
    status, body = await handle_workflow_register(
        WorkflowRegisterRequest(
            name="loan-approval",
            description="Auto-approve loans <50k USD",
            sector="financial-services",
            risk_threshold_escalate=0.40,
        ),
        workflow_registry=wf_reg,
        now=_NOW,
    )
    assert status == 200
    assert isinstance(body, WorkflowRegisterResponse)
    assert body.name == "loan-approval"
    assert body.sector == "financial-services"
    assert body.created_at == _NOW
    # And the registry actually got the row.
    row = await wf_reg.get(body.workflow_id)
    assert row is not None
    assert row.risk_threshold_escalate == pytest.approx(0.40)


async def test_workflow_register_uses_default_now_when_none() -> None:
    """now=None branch uses datetime.now(timezone.utc)."""
    import datetime as dt_mod

    wf_reg = InMemoryWorkflowRegistry()
    before = dt_mod.datetime.now(dt_mod.timezone.utc)
    status, body = await handle_workflow_register(
        WorkflowRegisterRequest(name="x"),
        workflow_registry=wf_reg,
    )
    after = dt_mod.datetime.now(dt_mod.timezone.utc)
    assert status == 200
    assert before <= body.created_at <= after


async def test_workflow_list_empty() -> None:
    wf_reg = InMemoryWorkflowRegistry()
    status, body = await handle_workflow_list(workflow_registry=wf_reg)
    assert status == 200
    assert isinstance(body, WorkflowListResponse)
    assert body.total == 0
    assert body.workflows == []


async def test_workflow_list_includes_agent_counts() -> None:
    """Register two workflows + two agents under WF1 + one under WF2;
    list_all reports correct agent_count per row."""
    wf_reg = InMemoryWorkflowRegistry()
    agent_reg = InMemoryAgentRegistry()
    # Wire the agent registry into the workflow registry so
    # count_agents can compute correctly.
    wf_reg._agent_registry = agent_reg

    _, wf1 = await handle_workflow_register(
        WorkflowRegisterRequest(name="wf1"),
        workflow_registry=wf_reg,
        now=_NOW,
    )
    _, wf2 = await handle_workflow_register(
        WorkflowRegisterRequest(name="wf2"),
        workflow_registry=wf_reg,
        now=_NOW,
    )

    # Two agents in wf1, one in wf2.
    for _ in range(2):
        await handle_agent_register(
            AgentRegisterRequest(
                workflow_id=wf1.workflow_id,
                spiffe_id=f"spiffe://x/{uuid.uuid4()}",
                role="loan-officer",
            ),
            workflow_registry=wf_reg,
            agent_registry=agent_reg,
            now=_NOW,
        )
    await handle_agent_register(
        AgentRegisterRequest(
            workflow_id=wf2.workflow_id,
            spiffe_id=f"spiffe://x/{uuid.uuid4()}",
            role="auditor",
        ),
        workflow_registry=wf_reg,
        agent_registry=agent_reg,
        now=_NOW,
    )

    status, body = await handle_workflow_list(workflow_registry=wf_reg)
    assert status == 200
    counts = {s.workflow_id: s.agent_count for s in body.workflows}
    assert counts[wf1.workflow_id] == 2
    assert counts[wf2.workflow_id] == 1


async def test_workflow_count_agents_returns_zero_when_no_agent_registry() -> None:
    """count_agents fallback path when _agent_registry is None."""
    wf_reg = InMemoryWorkflowRegistry()
    _, body = await handle_workflow_register(
        WorkflowRegisterRequest(name="solo"),
        workflow_registry=wf_reg,
        now=_NOW,
    )
    n = await wf_reg.count_agents(body.workflow_id)
    assert n == 0


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------


async def test_agent_register_success() -> None:
    wf_reg = InMemoryWorkflowRegistry()
    agent_reg = InMemoryAgentRegistry()
    _, wf_body = await handle_workflow_register(
        WorkflowRegisterRequest(name="wf"),
        workflow_registry=wf_reg,
        now=_NOW,
    )
    status, body = await handle_agent_register(
        AgentRegisterRequest(
            workflow_id=wf_body.workflow_id,
            spiffe_id="spiffe://example/agent/a1",
            role="loan-officer",
        ),
        workflow_registry=wf_reg,
        agent_registry=agent_reg,
        now=_NOW,
    )
    assert status == 200
    assert isinstance(body, AgentRegisterResponse)
    assert body.workflow_id == wf_body.workflow_id
    assert body.spiffe_id == "spiffe://example/agent/a1"


async def test_agent_register_unknown_workflow_returns_404() -> None:
    wf_reg = InMemoryWorkflowRegistry()
    agent_reg = InMemoryAgentRegistry()
    status, body = await handle_agent_register(
        AgentRegisterRequest(
            workflow_id=uuid.uuid4(),  # not registered
            spiffe_id="spiffe://x",
            role="x",
        ),
        workflow_registry=wf_reg,
        agent_registry=agent_reg,
        now=_NOW,
    )
    assert status == 404
    assert isinstance(body, ErrorResponse)
    assert body.error == "workflow_not_found"


async def test_agent_register_uses_default_now() -> None:
    """now=None default-arg branch."""
    import datetime as dt_mod

    wf_reg = InMemoryWorkflowRegistry()
    agent_reg = InMemoryAgentRegistry()
    _, wf_body = await handle_workflow_register(
        WorkflowRegisterRequest(name="wf"),
        workflow_registry=wf_reg,
        now=_NOW,
    )
    before = dt_mod.datetime.now(dt_mod.timezone.utc)
    _, body = await handle_agent_register(
        AgentRegisterRequest(
            workflow_id=wf_body.workflow_id,
            spiffe_id="s",
            role="r",
        ),
        workflow_registry=wf_reg,
        agent_registry=agent_reg,
    )
    after = dt_mod.datetime.now(dt_mod.timezone.utc)
    assert isinstance(body, AgentRegisterResponse)
    assert before <= body.created_at <= after


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


async def test_tool_register_success_with_no_workflow_restriction() -> None:
    wf_reg = InMemoryWorkflowRegistry()
    tool_reg = InMemoryToolRegistry()
    status, body = await handle_tool_register(
        ToolRegisterRequest(name="read_account_balance"),
        workflow_registry=wf_reg,
        tool_registry=tool_reg,
        now=_NOW,
    )
    assert status == 200
    assert isinstance(body, ToolRegisterResponse)
    assert body.name == "read_account_balance"
    assert body.allowed_workflow_ids == []


async def test_tool_register_success_with_workflow_restriction() -> None:
    wf_reg = InMemoryWorkflowRegistry()
    tool_reg = InMemoryToolRegistry()
    _, wf_body = await handle_workflow_register(
        WorkflowRegisterRequest(name="wf"),
        workflow_registry=wf_reg,
        now=_NOW,
    )
    status, body = await handle_tool_register(
        ToolRegisterRequest(
            name="transfer_funds",
            allowed_workflow_ids=[wf_body.workflow_id],
        ),
        workflow_registry=wf_reg,
        tool_registry=tool_reg,
        now=_NOW,
    )
    assert status == 200
    assert isinstance(body, ToolRegisterResponse)
    assert body.allowed_workflow_ids == [wf_body.workflow_id]


async def test_tool_register_unknown_workflow_in_restriction_returns_400() -> None:
    wf_reg = InMemoryWorkflowRegistry()
    tool_reg = InMemoryToolRegistry()
    fake_wf = uuid.uuid4()
    status, body = await handle_tool_register(
        ToolRegisterRequest(
            name="transfer_funds",
            allowed_workflow_ids=[fake_wf],
        ),
        workflow_registry=wf_reg,
        tool_registry=tool_reg,
        now=_NOW,
    )
    assert status == 400
    assert isinstance(body, ErrorResponse)
    assert body.error == "invalid_workflow_reference"


async def test_tool_register_uses_default_now() -> None:
    """now=None default-arg branch on tool handler."""
    import datetime as dt_mod

    wf_reg = InMemoryWorkflowRegistry()
    tool_reg = InMemoryToolRegistry()
    before = dt_mod.datetime.now(dt_mod.timezone.utc)
    _, body = await handle_tool_register(
        ToolRegisterRequest(name="t"),
        workflow_registry=wf_reg,
        tool_registry=tool_reg,
    )
    after = dt_mod.datetime.now(dt_mod.timezone.utc)
    assert isinstance(body, ToolRegisterResponse)
    assert before <= body.created_at <= after
