# =============================================================================
# Verixa Financial-Services Policy: Beneficiary Verification
# =============================================================================
# Requires that any transfer_funds tool_call cite a verified beneficiary in
# its context (input.context.beneficiary_verified == true). Implements a
# soft "second factor" pattern: even if the role is permitted and the amount
# under limit, an unverified beneficiary forces escalation.
#
# Output:
#   - decision: "pass" if not transfer_funds OR beneficiary_verified == true
#               "fail" otherwise
#   - reason: human-readable
#
# Regulatory anchors:
#   - PSD2 Art. 97 Strong Customer Authentication
#   - FFIEC IT Examination Handbook -- Authentication
# =============================================================================
package verixa.fs.beneficiary_verification

import rego.v1

default decision := "pass"

default reason := ""

# Fail: transfer_funds without beneficiary_verified=true
decision := "fail" if {
	input.action.tool_name == "transfer_funds"
	not input.context.beneficiary_verified == true
}

reason := "transfer_funds requires context.beneficiary_verified=true (PSD2 Art. 97 SCA)" if {
	input.action.tool_name == "transfer_funds"
	not input.context.beneficiary_verified == true
}
