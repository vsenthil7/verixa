# =============================================================================
# Verixa Core Policy: PII Redaction Enforcement
# =============================================================================
# Denies any governed action whose tool-call arguments contain unredacted PII
# (US Social Security Numbers, credit card numbers in PAN format).
#
# Input shape (matches docs/05_api A7 2.1 GovernRequest):
#   {
#     "agent_identity": {"spiffe_id": ..., "role": ..., "workflow_id": ...},
#     "action": {"type": "tool_call", "tool_name": ..., "arguments": {...}},
#     "context": {...}
#   }
#
# Output:
#   - decision: "pass" | "fail"
#   - reason: human-readable string when fail
#   - matched_pattern: which PII pattern triggered the deny (when fail)
#
# Regulatory anchors (informational; not legal advice):
#   - GDPR Art. 5(1)(c) data minimisation
#   - PCI-DSS 3.4 PAN protection
#
# Test fixtures: ./fixtures/pii_redaction_*.json
# =============================================================================
package verixa.core.pii_redaction

import rego.v1

# US SSN pattern: NNN-NN-NNNN with hyphens. We match conservatively (with
# hyphens only) to avoid false positives on 9-digit identifiers like ZIP+4.
ssn_pattern := `\b\d{3}-\d{2}-\d{4}\b`

# Visa/MC/Amex/Disc PAN pattern: 13-19 digit run, optionally hyphen/space
# separated in groups of 4. Matches both "4111-1111-1111-1111" and
# "4111111111111111" -- the firewall (CP-7) should already split-strip;
# this is a defence-in-depth check.
pan_pattern := `\b(?:\d[ -]?){13,19}\b`

# Default: pass. Rules below override to fail when PII is detected.
default decision := "pass"

default reason := ""

# ---------------------------------------------------------------------------
# Rule: deny if any string-valued argument matches the SSN pattern.
# ---------------------------------------------------------------------------
decision := "fail" if {
	pii_in_arguments
}

reason := msg if {
	pii_in_arguments
	msg := sprintf("argument %v contains an unredacted PII pattern: %v", [matched_arg, matched_pattern])
}

matched_pattern := "ssn" if {
	some _, value in input.action.arguments
	is_string(value)
	regex.match(ssn_pattern, value)
}

matched_pattern := "pan" if {
	some _, value in input.action.arguments
	is_string(value)
	regex.match(pan_pattern, value)
}

matched_arg := name if {
	some name, value in input.action.arguments
	is_string(value)
	regex.match(ssn_pattern, value)
}

matched_arg := name if {
	some name, value in input.action.arguments
	is_string(value)
	regex.match(pan_pattern, value)
}

pii_in_arguments if {
	some _, value in input.action.arguments
	is_string(value)
	regex.match(ssn_pattern, value)
}

pii_in_arguments if {
	some _, value in input.action.arguments
	is_string(value)
	regex.match(pan_pattern, value)
}
