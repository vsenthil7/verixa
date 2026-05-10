"""Tool Call Firewall -- allow-list enforcement (CP-7.1).

Pure-function evaluator. Given:
  - the candidate ``GovernAction`` (must be type='tool_call')
  - the caller's ``workflow_id``
  - a list of ``ToolRegistryEntry`` rows (read from verixa_registry.tools)

returns a ``FirewallVerdict(decision, reason, code)``.

Decision rules (evaluated in order; first match wins):
  1. action.type != 'tool_call' -> allow (this firewall doesn't apply)
  2. action.tool_name is None or empty -> deny (NO_TOOL_NAME)
  3. tool not in registry -> deny (TOOL_NOT_REGISTERED)
  4. tool inactive -> deny (TOOL_INACTIVE)
  5. tool's allowed_workflow_ids non-empty and workflow_id not in it -> deny
     (WORKFLOW_NOT_PERMITTED)
  6. otherwise -> allow

Empty allowed_workflow_ids on the registry entry means "any workflow"
(useful for system-wide tools like read_user_profile). Phase 1 may
swap this for an explicit ``allow_all_workflows`` boolean column.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from verixa_runtime.gateway.envelopes import GovernAction


class FirewallDecision(str, Enum):
    """Firewall outcomes (more granular than gateway Decision)."""

    ALLOW = "allow"
    DENY = "deny"


# Stable error codes -- callers (gateway, audit ledger) use these in
# log lines and customer-facing error messages without reading the
# free-text reason.
CODE_NO_TOOL_NAME: Final[str] = "firewall.no_tool_name"
CODE_TOOL_NOT_REGISTERED: Final[str] = "firewall.tool_not_registered"
CODE_TOOL_INACTIVE: Final[str] = "firewall.tool_inactive"
CODE_WORKFLOW_NOT_PERMITTED: Final[str] = "firewall.workflow_not_permitted"


@dataclass(frozen=True, slots=True)
class FirewallVerdict:
    """Result of a firewall evaluation."""

    decision: FirewallDecision
    reason: str
    code: str | None = None


@dataclass(frozen=True, slots=True)
class ToolRegistryEntry:
    """Subset of ``verixa_registry.tools`` the firewall needs.

    Frozen so callers can pass these around without worrying about
    accidental mutation between the registry read and the firewall
    decision.
    """

    name: str
    is_active: bool
    allowed_workflow_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)


def _find_entry(
    tool_name: str, registry: list[ToolRegistryEntry]
) -> ToolRegistryEntry | None:
    """Linear search. Phase 1 callers will pre-index by name."""
    for entry in registry:
        if entry.name == tool_name:
            return entry
    return None


def evaluate_allowlist(
    action: GovernAction,
    workflow_id: uuid.UUID,
    registry: list[ToolRegistryEntry],
) -> FirewallVerdict:
    """Evaluate the allow-list for ``action``.

    Returns a ``FirewallVerdict``. Never raises (firewall must be
    deterministic and total -- a panicked firewall is a deny by default
    at the gateway level, but this layer always produces a verdict).
    """
    # Rule 1: only tool_call actions are governed by this firewall.
    if action.type != "tool_call":
        return FirewallVerdict(
            decision=FirewallDecision.ALLOW,
            reason="firewall does not apply to non-tool_call actions",
        )

    # Rule 2: tool name is required for tool_call.
    tool_name = (action.tool_name or "").strip()
    if not tool_name:
        return FirewallVerdict(
            decision=FirewallDecision.DENY,
            reason="tool_call action requires a non-empty tool_name",
            code=CODE_NO_TOOL_NAME,
        )

    # Rule 3: tool must be in the registry.
    entry = _find_entry(tool_name, registry)
    if entry is None:
        return FirewallVerdict(
            decision=FirewallDecision.DENY,
            reason=f"tool {tool_name!r} is not registered",
            code=CODE_TOOL_NOT_REGISTERED,
        )

    # Rule 4: tool must be active.
    if not entry.is_active:
        return FirewallVerdict(
            decision=FirewallDecision.DENY,
            reason=f"tool {tool_name!r} is not active",
            code=CODE_TOOL_INACTIVE,
        )

    # Rule 5: workflow gating. Empty allowed_workflow_ids = any workflow.
    if entry.allowed_workflow_ids and workflow_id not in entry.allowed_workflow_ids:
        return FirewallVerdict(
            decision=FirewallDecision.DENY,
            reason=(
                f"tool {tool_name!r} is not permitted for "
                f"workflow_id={workflow_id}"
            ),
            code=CODE_WORKFLOW_NOT_PERMITTED,
        )

    return FirewallVerdict(
        decision=FirewallDecision.ALLOW,
        reason="allow-list passed",
    )
