"""Control Plane registry handlers (CP-14.4).

Three small CRUD-style registries: WorkflowRegistry,
AgentRegistry, ToolRegistry. Phase-0 ships in-memory dict-backed
implementations. Phase-1 swaps for Postgres backings via the CP-3
schema (verixa_registry.workflows, verixa_registry.agents,
verixa_registry.tools).

Each registry exposes two operations:
  - register: take a typed request, mint a new ID, store the row,
    return the typed response.
  - list (workflows only): return summary rows + total count.

Cross-registry rules:
  - An agent's workflow_id must reference an existing workflow.
  - A tool may restrict to a list of workflow_ids; those must exist
    too. Empty list means "any workflow".

These rules are enforced in the handler, not in the registry, so
the registry stays as a pure key-value store.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from verixa_control_plane.envelopes import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    ErrorResponse,
    ToolRegisterRequest,
    ToolRegisterResponse,
    WorkflowListResponse,
    WorkflowRegisterRequest,
    WorkflowRegisterResponse,
    WorkflowSummary,
)


# ---------------------------------------------------------------------------
# Row types (private to the registry layer)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkflowRow:
    workflow_id: uuid.UUID
    name: str
    description: str
    sector: str
    risk_threshold_escalate: float
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AgentRow:
    agent_id: uuid.UUID
    workflow_id: uuid.UUID
    spiffe_id: str
    role: str
    description: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ToolRow:
    tool_id: uuid.UUID
    name: str
    description: str
    is_active: bool
    allowed_workflow_ids: tuple[uuid.UUID, ...]
    created_at: datetime


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class WorkflowRegistry(Protocol):
    async def register(
        self, row: WorkflowRow
    ) -> None:  # pragma: no cover -- Protocol body
        ...

    async def get(
        self, workflow_id: uuid.UUID
    ) -> WorkflowRow | None:  # pragma: no cover -- Protocol body
        ...

    async def list_all(
        self,
    ) -> list[WorkflowRow]:  # pragma: no cover -- Protocol body
        ...

    async def count_agents(
        self, workflow_id: uuid.UUID
    ) -> int:  # pragma: no cover -- Protocol body
        ...


class AgentRegistry(Protocol):
    async def register(
        self, row: AgentRow
    ) -> None:  # pragma: no cover -- Protocol body
        ...

    async def count_for_workflow(
        self, workflow_id: uuid.UUID
    ) -> int:  # pragma: no cover -- Protocol body
        ...


class ToolRegistry(Protocol):
    async def register(
        self, row: ToolRow
    ) -> None:  # pragma: no cover -- Protocol body
        ...


# ---------------------------------------------------------------------------
# In-memory implementations
# ---------------------------------------------------------------------------


class InMemoryWorkflowRegistry:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, WorkflowRow] = {}
        self._lock = asyncio.Lock()
        # Wired by handle_agent_register so list_all can report agent counts.
        self._agent_registry: InMemoryAgentRegistry | None = None

    async def register(self, row: WorkflowRow) -> None:
        async with self._lock:
            self._items[row.workflow_id] = row

    async def get(self, workflow_id: uuid.UUID) -> WorkflowRow | None:
        async with self._lock:
            return self._items.get(workflow_id)

    async def list_all(self) -> list[WorkflowRow]:
        async with self._lock:
            return list(self._items.values())

    async def count_agents(self, workflow_id: uuid.UUID) -> int:
        if self._agent_registry is None:
            return 0
        return await self._agent_registry.count_for_workflow(workflow_id)


class InMemoryAgentRegistry:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, AgentRow] = {}
        self._lock = asyncio.Lock()

    async def register(self, row: AgentRow) -> None:
        async with self._lock:
            self._items[row.agent_id] = row

    async def count_for_workflow(self, workflow_id: uuid.UUID) -> int:
        async with self._lock:
            return sum(
                1 for r in self._items.values()
                if r.workflow_id == workflow_id
            )


class InMemoryToolRegistry:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, ToolRow] = {}
        self._lock = asyncio.Lock()

    async def register(self, row: ToolRow) -> None:
        async with self._lock:
            self._items[row.tool_id] = row


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def handle_workflow_register(
    req: WorkflowRegisterRequest,
    *,
    workflow_registry: WorkflowRegistry,
    now: datetime | None = None,
) -> tuple[int, WorkflowRegisterResponse]:
    """POST /v1/control/workflows."""
    ts = now or _now_utc()
    row = WorkflowRow(
        workflow_id=uuid.uuid4(),
        name=req.name,
        description=req.description,
        sector=req.sector,
        risk_threshold_escalate=req.risk_threshold_escalate,
        created_at=ts,
    )
    await workflow_registry.register(row)
    return 200, WorkflowRegisterResponse(
        workflow_id=row.workflow_id,
        name=row.name,
        sector=row.sector,
        created_at=row.created_at,
    )


async def handle_workflow_list(
    *,
    workflow_registry: WorkflowRegistry,
) -> tuple[int, WorkflowListResponse]:
    """GET /v1/control/workflows."""
    rows = await workflow_registry.list_all()
    summaries = [
        WorkflowSummary(
            workflow_id=r.workflow_id,
            name=r.name,
            sector=r.sector,
            risk_threshold_escalate=r.risk_threshold_escalate,
            agent_count=await workflow_registry.count_agents(r.workflow_id),
            created_at=r.created_at,
        )
        for r in rows
    ]
    return 200, WorkflowListResponse(
        workflows=summaries, total=len(summaries)
    )


async def handle_agent_register(
    req: AgentRegisterRequest,
    *,
    workflow_registry: WorkflowRegistry,
    agent_registry: AgentRegistry,
    now: datetime | None = None,
) -> tuple[int, AgentRegisterResponse | ErrorResponse]:
    """POST /v1/control/agents.

    Validates that the referenced workflow_id exists before
    registering the agent. Unknown workflow -> 404.
    """
    workflow = await workflow_registry.get(req.workflow_id)
    if workflow is None:
        return 404, ErrorResponse(
            error="workflow_not_found",
            message=f"no workflow registered for workflow_id={req.workflow_id}",
        )
    ts = now or _now_utc()
    row = AgentRow(
        agent_id=uuid.uuid4(),
        workflow_id=req.workflow_id,
        spiffe_id=req.spiffe_id,
        role=req.role,
        description=req.description,
        created_at=ts,
    )
    await agent_registry.register(row)
    return 200, AgentRegisterResponse(
        agent_id=row.agent_id,
        workflow_id=row.workflow_id,
        spiffe_id=row.spiffe_id,
        role=row.role,
        created_at=row.created_at,
    )


async def handle_tool_register(
    req: ToolRegisterRequest,
    *,
    workflow_registry: WorkflowRegistry,
    tool_registry: ToolRegistry,
    now: datetime | None = None,
) -> tuple[int, ToolRegisterResponse | ErrorResponse]:
    """POST /v1/control/tools.

    If allowed_workflow_ids is non-empty, every referenced workflow
    must exist. Unknown workflow -> 400 invalid_workflow_reference
    (not 404, because it's a malformed request rather than a missing
    resource at the endpoint's own URL).
    """
    for wf_id in req.allowed_workflow_ids:
        if await workflow_registry.get(wf_id) is None:
            return 400, ErrorResponse(
                error="invalid_workflow_reference",
                message=(
                    f"allowed_workflow_ids references unknown "
                    f"workflow_id={wf_id}"
                ),
            )
    ts = now or _now_utc()
    row = ToolRow(
        tool_id=uuid.uuid4(),
        name=req.name,
        description=req.description,
        is_active=req.is_active,
        allowed_workflow_ids=tuple(req.allowed_workflow_ids),
        created_at=ts,
    )
    await tool_registry.register(row)
    return 200, ToolRegisterResponse(
        tool_id=row.tool_id,
        name=row.name,
        is_active=row.is_active,
        allowed_workflow_ids=list(row.allowed_workflow_ids),
        created_at=row.created_at,
    )


__all__ = [
    "AgentRegistry",
    "AgentRow",
    "InMemoryAgentRegistry",
    "InMemoryToolRegistry",
    "InMemoryWorkflowRegistry",
    "ToolRegistry",
    "ToolRow",
    "WorkflowRegistry",
    "WorkflowRow",
    "handle_agent_register",
    "handle_tool_register",
    "handle_workflow_list",
    "handle_workflow_register",
]
