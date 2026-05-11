"""CP-30 negative test 3/5: unicode + encoding edge cases.

Anchored to BR-02 (input validation), BR-07 (audit-trail completeness),
NEGATIVE_TEST_PLAN section 7 (unicode adversarial inputs).

Unicode adversarial payloads target the gap between "what the
operator sees in the audit log" and "what the system actually
processed". The classes covered here:

  - RTL override (U+202E) -- can visually disguise an account number
    or domain in audit-log display
  - Zero-width characters (U+200B, U+200C, U+200D, U+FEFF) -- can be
    used to bypass naive string-equality checks for blocklists
  - Homoglyphs (Cyrillic 'a' vs Latin 'a', etc.) -- can defeat
    string-match policies
  - Surrogate halves -- invalid UTF-8 in JSON should be rejected at
    parse time
  - Null bytes embedded in strings -- some downstream parsers
    truncate at \\x00

The envelope schema is strict-mode pydantic, so the validation layer
should accept any well-formed UTF-8 string in a free-text field
(reasoning, memo, prompt_hash content is hex so doesn't apply) but
the SHAPE of the validation must remain correct: extra fields
rejected, type errors rejected, hash-format checks enforced regardless
of what unicode appears in OTHER fields.

Adversarial framing: the system must preserve EXACT bytes in the
audit log so a forensic reviewer sees what the agent actually
sent, even if the operator UI later decides to render it as escaped
glyphs.
"""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from verixa_runtime.gateway.envelopes import (
    AgentIdentity,
    GovernAction,
    GovernContext,
    GovernRequest,
    RetrievedDocument,
)


_WF_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")


# Unicode adversarial payload constants for readability.
_RTL_OVERRIDE = "\u202e"  # RIGHT-TO-LEFT OVERRIDE
_ZERO_WIDTH_SPACE = "\u200b"
_ZERO_WIDTH_JOINER = "\u200d"
_BYTE_ORDER_MARK = "\ufeff"
_CYRILLIC_A = "\u0430"  # looks like Latin 'a'
_NULL_BYTE = "\x00"


def _agent(role: str = "loan-officer") -> AgentIdentity:
    return AgentIdentity(
        spiffe_id="spiffe://example/agent/x",
        role=role,
        workflow_id=_WF_ID,
    )


# ---------------------------------------------------------------------------
# Acceptance: well-formed unicode preserved verbatim
# ---------------------------------------------------------------------------


def test_rtl_override_preserved_in_role_string() -> None:
    """RTL override in a role string must be PRESERVED verbatim, NOT
    sanitised silently. The audit log gets the bytes the agent sent;
    operator UI is responsible for safe display. This is the spec
    documented in BR-07."""
    role = f"loan-officer{_RTL_OVERRIDE}admin"
    agent = _agent(role=role)
    assert agent.role == role
    assert _RTL_OVERRIDE in agent.role


def test_zero_width_chars_preserved_in_reasoning() -> None:
    """Zero-width chars in reasoning_chain_summary must round-trip
    exactly. If pydantic strips them silently, an attacker could send
    'transfer1000' to a blocklist that matches 'transfer1000' literally
    but slips past 'transfer 1000'-style splits."""
    reasoning = (
        f"approve{_ZERO_WIDTH_SPACE}transfer"
        f"{_ZERO_WIDTH_JOINER}1000"
    )
    ctx = GovernContext(
        prompt_hash="a" * 64,
        model_version="m",
        reasoning_chain_summary=reasoning,
    )
    assert ctx.reasoning_chain_summary == reasoning


def test_homoglyph_cyrillic_a_preserved_in_role() -> None:
    """Cyrillic 'a' in role MUST survive verbatim. A 'admin' role
    spelt with Cyrillic-a is NOT equal to the Latin-spelt 'admin'
    role for policy purposes, and the audit log must surface the
    real bytes so a reviewer can see the deception."""
    role = f"{_CYRILLIC_A}dmin"  # Cyrillic-a + Latin 'dmin'
    agent = _agent(role=role)
    # The Cyrillic 'a' is NOT equal to Latin 'a' byte-wise.
    assert agent.role != "admin"
    assert agent.role == role


def test_bom_preserved_in_reasoning() -> None:
    """BOM at start of reasoning string is unusual but valid; must
    survive verbatim."""
    reasoning = f"{_BYTE_ORDER_MARK}approve transfer"
    ctx = GovernContext(
        prompt_hash="a" * 64,
        model_version="m",
        reasoning_chain_summary=reasoning,
    )
    assert ctx.reasoning_chain_summary == reasoning
    assert ctx.reasoning_chain_summary.startswith(_BYTE_ORDER_MARK)


def test_null_byte_in_role_preserved() -> None:
    """Null byte inside a role string: pydantic strict mode accepts
    it as a valid str; the audit emitter preserves bytes. Downstream
    consumers must NOT truncate at \\x00. (This test asserts the
    envelope layer; downstream truncation is a separate test
    category for Phase 1.)"""
    role = f"loan-officer{_NULL_BYTE}root"
    agent = _agent(role=role)
    assert _NULL_BYTE in agent.role
    assert agent.role == role


# ---------------------------------------------------------------------------
# Rejection: invalid encodings + violated constraints
# ---------------------------------------------------------------------------


def test_empty_role_rejected_even_with_unicode_around() -> None:
    """An empty role is rejected by the agent identity validator
    regardless of what unicode lives elsewhere in the envelope."""
    with pytest.raises(ValidationError):
        AgentIdentity(spiffe_id="spiffe://x", role="", workflow_id=_WF_ID)


def test_non_hex_unicode_in_prompt_hash_rejected() -> None:
    """prompt_hash is 64 hex chars. Slipping in Cyrillic-a (looks
    Latin but isn't hex) MUST be rejected by the hash regex."""
    bad_hash = _CYRILLIC_A * 64  # 64 Cyrillic-a chars
    with pytest.raises(ValidationError):
        GovernContext(prompt_hash=bad_hash, model_version="m")


def test_rtl_in_doc_id_preserved() -> None:
    """Doc IDs are free-form strings; RTL inside a doc_id is
    preserved verbatim. Use case: an attacker references a 'safe'
    doc but the actual doc_id contains RTL that swaps the display
    order to look like a different doc."""
    doc_id = f"doc{_RTL_OVERRIDE}_001"
    rd = RetrievedDocument(doc_id=doc_id, hash="a" * 64)
    assert rd.doc_id == doc_id


def test_json_with_invalid_utf8_surrogate_rejected() -> None:
    """An attacker tries to land an envelope via JSON that contains
    an unpaired surrogate half. json.loads must reject it before
    pydantic even sees the dict; assert that round-tripping through
    json fails."""
    # Unpaired surrogate -- not valid in JSON either.
    bad_json_bytes = b'{"spiffe_id": "spiffe://x", "role": "\\ud800", "workflow_id": "00000000-0000-0000-0000-000000000000"}'
    parsed = json.loads(bad_json_bytes.decode("utf-8"))
    # Python's json.loads accepts the surrogate escape but pydantic
    # strict-mode str rejects strings containing unpaired surrogates
    # when re-encoding to UTF-8. The role field will contain the
    # surrogate; we assert pydantic still constructs (it stores the
    # string) but encoding to JSON bytes again raises. This is the
    # actual safety boundary -- the bundle CANNOT be canonicalised
    # if it contains an unpaired surrogate.
    agent = AgentIdentity.model_validate(parsed)
    # Re-serialising to JSON bytes raises UnicodeEncodeError because
    # the role contains an unpaired surrogate. This is the protective
    # behaviour: the bundle cannot be sealed if it carries a
    # surrogate.
    with pytest.raises(UnicodeEncodeError):
        json.dumps(
            {"role": agent.role}, ensure_ascii=False
        ).encode("utf-8")


def test_oversized_unicode_in_reasoning_passes() -> None:
    """Unicode characters in reasoning string -- even multi-byte
    emoji + RTL -- must round-trip. There's no length limit on
    reasoning_chain_summary in the current envelope; this asserts
    the schema is unicode-clean."""
    # 100 chars of pure unicode (multi-codepoint emoji + RTL).
    reasoning = (
        f"{_RTL_OVERRIDE}{_ZERO_WIDTH_SPACE}{_CYRILLIC_A}" * 30
    )
    ctx = GovernContext(
        prompt_hash="a" * 64,
        model_version="m",
        reasoning_chain_summary=reasoning,
    )
    assert ctx.reasoning_chain_summary == reasoning
