# =============================================================================
# Verixa Financial-Services Policy: Transfer Amount Limit (by role)
# =============================================================================
# Caps the maximum transfer amount based on the agent's role. Phase 0
# table is hard-coded; CP-12 reads from verixa_registry.policies.
#
# Limit table (GBP):
#   role             | limit
#   -----------------|-------
#   junior-clerk     |   1000
#   loan-officer     |  10000
#   senior-officer   |  50000
#   admin            | 999999  (effectively unbounded for hackathon)
#
# Currency conversion: out of scope for Phase 0; the policy assumes the
# arguments.amount is already in GBP. CP-9 will normalise via FX rates.
#
# Trigger: only applies when action.tool_name == "transfer_funds".
# Other tool calls bypass this policy (decision: pass).
#
# Output:
#   - decision: "pass" | "fail"
#   - reason: human-readable string
# =============================================================================
package verixa.fs.transfer_amount_limit

import rego.v1

limit := {
	"junior-clerk": 1000,
	"loan-officer": 10000,
	"senior-officer": 50000,
	"admin": 999999,
}

# Default: pass (this policy doesn't apply)
default decision := "pass"

default reason := ""

# Pass: amount under role's limit
decision := "pass" if {
	input.action.tool_name == "transfer_funds"
	role := input.agent_identity.role
	role_limit := limit[role]
	input.action.arguments.amount <= role_limit
}

# Fail: amount above role's limit
decision := "fail" if {
	input.action.tool_name == "transfer_funds"
	role := input.agent_identity.role
	role_limit := limit[role]
	input.action.arguments.amount > role_limit
}

# Fail: role not in limit table for transfer_funds
decision := "fail" if {
	input.action.tool_name == "transfer_funds"
	role := input.agent_identity.role
	not limit[role]
}

reason := msg if {
	input.action.tool_name == "transfer_funds"
	role := input.agent_identity.role
	role_limit := limit[role]
	input.action.arguments.amount > role_limit
	msg := sprintf(
		"transfer amount %v exceeds role limit %v for role %v",
		[input.action.arguments.amount, role_limit, role],
	)
}

reason := msg if {
	input.action.tool_name == "transfer_funds"
	role := input.agent_identity.role
	not limit[role]
	msg := sprintf("role %v has no transfer_funds authorisation", [role])
}
