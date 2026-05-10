"""pytest suite for verixa_runtime.firewall.allowlist (CP-7.1).

100% line + branch coverage on the allow-list evaluator.
"""

from __future__ import annotations

import uuid

import pytest

from verixa_runtime.firewall.allowlist import (
    CODE_NO_TOOL_NAME,
    CODE_TOOL_INACTIVE,
    CODE_TOOL_NOT_REGISTERED,
    CODE_WORKFLOW_NOT_PERMITTED,
    FirewallDecision,
    FirewallVerdict,
    ToolRegistryEntry,
    evaluate_allowlist,
)
from verixa_runtime.gateway.envelopes import GovernAction


WF_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
WF_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _action(
    type_: str = "tool_call",
    tool_name: str | None = "transfer_funds",
    arguments: dict | None = None,
) -> GovernAction:
    payload: dict = {"type": type_, "arguments": arguments or {}}
    if tool_name is not None:
        payload["tool_name"] = tool_name
    return GovernAction.model_validate(payload)


# ---------------------------------------------------------------------------
# Enums + constants
# ---------------------------------------------------------------------------


def test_decision_values() -> None:
    assert FirewallDecision.ALLOW.value == "allow"
    assert FirewallDecision.DENY.value == "deny"


def test_error_codes_namespaced() -> None:
    for code in (
        CODE_NO_TOOL_NAME,
        CODE_TOOL_NOT_REGISTERED,
        CODE_TOOL_INACTIVE,
        CODE_WORKFLOW_NOT_PERMITTED,
    ):
        assert code.startswith("firewall.")


def test_verdict_is_frozen() -> None:
    v = FirewallVerdict(decision=FirewallDecision.ALLOW, reason="ok")
    with pytest.raises((AttributeError, Exception)):
        v.decision = FirewallDecision.DENY  # type: ignore[misc]


def test_registry_entry_is_frozen() -> None:
    e = ToolRegistryEntry(name="x", is_active=True)
    with pytest.raises((AttributeError, Exception)):
        e.is_active = False  # type: ignore[misc]


def test_registry_entry_default_workflow_ids_is_empty_tuple() -> None:
    e = ToolRegistryEntry(name="x", is_active=True)
    assert e.allowed_workflow_ids == ()


# ---------------------------------------------------------------------------
# Rule 1: non-tool_call actions bypass the firewall
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind", ["model_invocation", "data_access", "external_api"]
)
def test_non_tool_call_actions_pass_through(kind: str) -> None:
    action = _action(type_=kind, tool_name=None)
    verdict = evaluate_allowlist(action, WF_A, registry=[])
    assert verdict.decision == FirewallDecision.ALLOW
    assert verdict.code is None


# ---------------------------------------------------------------------------
# Rule 2: missing/empty tool_name on tool_call -> deny
# ---------------------------------------------------------------------------


def test_tool_call_without_tool_name_is_denied() -> None:
    action = _action(tool_name=None)
    verdict = evaluate_allowlist(action, WF_A, registry=[])
    assert verdict.decision == FirewallDecision.DENY
    assert verdict.code == CODE_NO_TOOL_NAME


def test_tool_call_with_whitespace_tool_name_is_denied() -> None:
    action = _action(tool_name="   ")
    verdict = evaluate_allowlist(action, WF_A, registry=[])
    assert verdict.decision == FirewallDecision.DENY
    assert verdict.code == CODE_NO_TOOL_NAME


# ---------------------------------------------------------------------------
# Rule 3: unknown tool -> deny
# ---------------------------------------------------------------------------


def test_unknown_tool_is_denied() -> None:
    action = _action(tool_name="unknown_tool")
    registry = [ToolRegistryEntry(name="other_tool", is_active=True)]
    verdict = evaluate_allowlist(action, WF_A, registry)
    assert verdict.decision == FirewallDecision.DENY
    assert verdict.code == CODE_TOOL_NOT_REGISTERED
    assert "unknown_tool" in verdict.reason


def test_empty_registry_denies_any_named_tool() -> None:
    action = _action(tool_name="x")
    verdict = evaluate_allowlist(action, WF_A, registry=[])
    assert verdict.decision == FirewallDecision.DENY
    assert verdict.code == CODE_TOOL_NOT_REGISTERED


# ---------------------------------------------------------------------------
# Rule 4: inactive tool -> deny
# ---------------------------------------------------------------------------


def test_inactive_tool_is_denied() -> None:
    action = _action(tool_name="transfer_funds")
    registry = [
        ToolRegistryEntry(
            name="transfer_funds",
            is_active=False,
            allowed_workflow_ids=(WF_A,),
        ),
    ]
    verdict = evaluate_allowlist(action, WF_A, registry)
    assert verdict.decision == FirewallDecision.DENY
    assert verdict.code == CODE_TOOL_INACTIVE


# ---------------------------------------------------------------------------
# Rule 5: workflow not permitted -> deny
# ---------------------------------------------------------------------------


def test_workflow_not_in_allowed_list_denied() -> None:
    action = _action(tool_name="transfer_funds")
    registry = [
        ToolRegistryEntry(
            name="transfer_funds",
            is_active=True,
            allowed_workflow_ids=(WF_A,),
        ),
    ]
    # Caller is on WF_B, which isn't allowed
    verdict = evaluate_allowlist(action, WF_B, registry)
    assert verdict.decision == FirewallDecision.DENY
    assert verdict.code == CODE_WORKFLOW_NOT_PERMITTED
    assert str(WF_B) in verdict.reason


def test_workflow_in_allowed_list_passes() -> None:
    action = _action(tool_name="transfer_funds")
    registry = [
        ToolRegistryEntry(
            name="transfer_funds",
            is_active=True,
            allowed_workflow_ids=(WF_A, WF_B),
        ),
    ]
    verdict = evaluate_allowlist(action, WF_A, registry)
    assert verdict.decision == FirewallDecision.ALLOW
    assert verdict.code is None


def test_empty_allowed_workflow_ids_means_any_workflow() -> None:
    """Tools with no per-workflow restriction (e.g. read_user_profile) pass."""
    action = _action(tool_name="read_user_profile")
    registry = [
        ToolRegistryEntry(
            name="read_user_profile",
            is_active=True,
            allowed_workflow_ids=(),  # any workflow
        ),
    ]
    verdict = evaluate_allowlist(action, WF_A, registry)
    assert verdict.decision == FirewallDecision.ALLOW


# ---------------------------------------------------------------------------
# Order independence + multi-entry registries
# ---------------------------------------------------------------------------


def test_match_works_when_target_is_not_first_in_registry() -> None:
    action = _action(tool_name="transfer_funds")
    registry = [
        ToolRegistryEntry(name="other1", is_active=True),
        ToolRegistryEntry(name="other2", is_active=True),
        ToolRegistryEntry(
            name="transfer_funds",
            is_active=True,
            allowed_workflow_ids=(WF_A,),
        ),
    ]
    verdict = evaluate_allowlist(action, WF_A, registry)
    assert verdict.decision == FirewallDecision.ALLOW


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_firewall_package_reexports() -> None:
    from verixa_runtime import firewall

    for name in (
        "FirewallDecision",
        "FirewallVerdict",
        "ToolRegistryEntry",
        "evaluate_allowlist",
    ):
        assert hasattr(firewall, name), f"firewall package missing {name}"
