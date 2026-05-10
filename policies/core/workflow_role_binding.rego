# =============================================================================
# Verixa Core Policy: Workflow-Role Binding
# =============================================================================
# Denies any governed action whose agent role is not authorised for the
# action.type within the caller's workflow.
#
# Phase 0 binding table (hard-coded; CP-12 reads from verixa_registry):
#   role             | allowed action types
#   -----------------|------------------------------------------------
#   loan-officer     | tool_call, model_invocation
#   audit-readonly   | model_invocation
#   admin            | tool_call, model_invocation, data_access, external_api
#
# Any other role -- or any role attempting an action type not in its row --
# fails the policy.
#
# Output:
#   - decision: "pass" | "fail"
#   - reason: human-readable string when fail
# =============================================================================
package verixa.core.workflow_role_binding

import rego.v1

# Role -> set of permitted action types (Rego sets are objects with
# value=true entries; using object form for readability).
allowed := {
	"loan-officer": {"tool_call", "model_invocation"},
	"audit-readonly": {"model_invocation"},
	"admin": {"tool_call", "model_invocation", "data_access", "external_api"},
}

default decision := "fail"

default reason := "role not recognised or action type not permitted for this role"

decision := "pass" if {
	role := input.agent_identity.role
	action_type := input.action.type
	allowed[role][action_type]
}

reason := "" if {
	role := input.agent_identity.role
	action_type := input.action.type
	allowed[role][action_type]
}
