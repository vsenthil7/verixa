"""CP-30 negative test 4/5: size-limit + structural-depth edges.

Anchored to BR-02 (input validation), NEGATIVE_TEST_PLAN section 8
(size-bomb / nested-payload defences).

A "size bomb" attack tries to exhaust server resources by submitting
either:
  - very long strings in unbounded fields
  - deeply-nested JSON objects in request_envelope or arguments
  - very large arrays in retrieved_documents
  - very large numeric values in risk_score (out of range)

The defences in Verixa Phase 0:
  - retrieved_document hash MUST be exactly 64 hex chars (length
    invariant; cannot be inflated)
  - prompt_hash MUST be exactly 64 hex chars (same)
  - risk_score MUST be in [0.0, 1.0] (numeric range invariant)
  - bundle.canonicalise produces deterministic output regardless of
    nesting depth (no recursion explosion in our code)

These tests exercise: oversized strings where the schema allows
them (must round-trip), oversized strings where the schema enforces
length (must reject), deep nesting in request_envelope (must
canonicalise without stack overflow), very long arrays of retrieved
documents (must canonicalise deterministically).

Adversarial framing: an attacker submits "transfer 50" with a
1-megabyte reasoning_chain_summary. The audit ledger should accept
it (we promise byte-fidelity) but the storage layer must scale
linearly. We can't test storage here, but we can test that the
serialisation path doesn't blow up at the envelope layer.
"""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from verixa_runtime.gateway.envelopes import (
    AgentIdentity,
    GovernContext,
    RetrievedDocument,
)
from verixa_runtime.replay import (
    ReplayBundle,
    canonicalise_bundle,
    deserialise_bundle,
)


_WF_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
_AUDIT_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
_TENANT_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")


def _bundle_with_envelope(envelope: dict[str, object]) -> ReplayBundle:
    return ReplayBundle(
        audit_id=_AUDIT_ID,
        tenant_id=_TENANT_ID,
        decision="allow",
        risk_score=0.1,
        request_envelope=envelope,
        timestamp_unix_ns=1_700_000_000_000_000_000,
    )


# ---------------------------------------------------------------------------
# Oversized fields where schema is open (must preserve verbatim)
# ---------------------------------------------------------------------------


def test_very_long_reasoning_chain_summary_round_trips() -> None:
    """100 KB of reasoning text -- unbounded by current schema --
    must round-trip exactly. Establishes that there's no silent
    truncation at the pydantic layer."""
    big = "x" * 100_000
    ctx = GovernContext(
        prompt_hash="a" * 64,
        model_version="m",
        reasoning_chain_summary=big,
    )
    assert ctx.reasoning_chain_summary == big
    assert len(ctx.reasoning_chain_summary) == 100_000


def test_very_long_spiffe_id_round_trips() -> None:
    """SPIFFE IDs in practice are short; the schema allows long ones
    so an attacker substituting a 10 KB spiffe URI lands in the audit
    log verbatim. Defence is preservation, not truncation."""
    big_spiffe = "spiffe://example/" + ("a" * 10_000)
    agent = AgentIdentity(spiffe_id=big_spiffe, role="r", workflow_id=_WF_ID)
    assert agent.spiffe_id == big_spiffe


def test_long_array_of_retrieved_documents_canonicalises() -> None:
    """1000 retrieved documents in a single envelope. canonicalise
    must produce deterministic bytes; deserialise must round-trip."""
    docs = tuple(
        (f"doc_{i:04d}", f"{i:0>64x}"[:64]) for i in range(1000)
    )
    b = ReplayBundle(
        audit_id=_AUDIT_ID,
        tenant_id=_TENANT_ID,
        decision="allow",
        risk_score=0.1,
        request_envelope={"action": "x"},
        retrieved_documents=docs,
        timestamp_unix_ns=1_700_000_000_000_000_000,
    )
    bytes_out = canonicalise_bundle(b)
    # Determinism over large payload.
    assert canonicalise_bundle(b) == bytes_out
    # Round-trip preserves count.
    b2 = deserialise_bundle(bytes_out)
    assert len(b2.retrieved_documents) == 1000


# ---------------------------------------------------------------------------
# Oversized fields where schema enforces length (must reject)
# ---------------------------------------------------------------------------


def test_too_long_hash_rejected() -> None:
    """retrieved-document hash MUST be exactly 64 chars. 65 chars is
    rejected by validator -- length invariant defended."""
    with pytest.raises(ValidationError):
        RetrievedDocument(doc_id="x", hash="a" * 65)


def test_too_short_hash_rejected() -> None:
    """And 63 chars is rejected -- you cannot shrink the hash either."""
    with pytest.raises(ValidationError):
        RetrievedDocument(doc_id="x", hash="a" * 63)


def test_empty_doc_id_in_replay_bundle_rejected() -> None:
    """retrieved-document doc_id must be a non-empty string in the
    bundle validator. An empty doc_id would mean a hash without an
    anchor -- the validator catches it."""
    with pytest.raises(ValueError, match="retrieved_documents"):
        ReplayBundle(
            audit_id=_AUDIT_ID,
            tenant_id=_TENANT_ID,
            decision="allow",
            risk_score=0.1,
            request_envelope={"a": 1},
            retrieved_documents=(("", "a" * 64),),
            timestamp_unix_ns=1_700_000_000_000_000_000,
        )


# ---------------------------------------------------------------------------
# Risk-score range
# ---------------------------------------------------------------------------


def test_risk_score_above_one_rejected_in_bundle() -> None:
    """risk_score > 1.0 in the bundle MUST be rejected. Float
    inflation attack: an attacker who can mutate one byte in the
    bundle tries to set risk to 99.0 to look 'very dangerous'
    (potentially DoSing review queues). Bundle validator rejects."""
    with pytest.raises(ValueError, match="risk_score"):
        ReplayBundle(
            audit_id=_AUDIT_ID,
            tenant_id=_TENANT_ID,
            decision="allow",
            risk_score=99.0,
            request_envelope={"a": 1},
            timestamp_unix_ns=1_700_000_000_000_000_000,
        )


def test_risk_score_below_zero_rejected_in_bundle() -> None:
    """And risk_score < 0.0 in the bundle MUST be rejected. Defence
    against an attacker trying to deflate risk to negative for a
    low-priority queue."""
    with pytest.raises(ValueError, match="risk_score"):
        ReplayBundle(
            audit_id=_AUDIT_ID,
            tenant_id=_TENANT_ID,
            decision="allow",
            risk_score=-0.5,
            request_envelope={"a": 1},
            timestamp_unix_ns=1_700_000_000_000_000_000,
        )


# ---------------------------------------------------------------------------
# Deeply nested request envelope
# ---------------------------------------------------------------------------


def test_deep_nested_envelope_canonicalises_without_recursion_error() -> None:
    """200 levels of nested dict in request_envelope. canonicalise
    must produce deterministic bytes without RecursionError.

    Adversarial scenario: attacker submits a deeply nested payload
    hoping to cause a stack overflow in json.dumps. Python's json
    library has a default recursion limit but we're well under it
    at 200 levels."""
    deep: dict[str, object] = {"x": 1}
    cur = deep
    for _ in range(200):
        new: dict[str, object] = {"x": 1}
        cur["nested"] = new
        cur = new
    b = _bundle_with_envelope(deep)
    bytes_out = canonicalise_bundle(b)
    # Determinism over deep payload.
    assert canonicalise_bundle(b) == bytes_out
    # And the deserialise path doesn't fail either.
    b2 = deserialise_bundle(bytes_out)
    # Walk down 200 levels to confirm round-trip.
    walker = b2.request_envelope
    for _ in range(200):
        assert isinstance(walker, dict)
        walker = walker["nested"]


def test_extremely_long_string_value_in_envelope_canonicalises() -> None:
    """1 MB string as a single value in request_envelope. canonicalise
    must complete without OOM and produce deterministic output."""
    big = "x" * 1_000_000
    b = _bundle_with_envelope({"large_field": big})
    bytes_out = canonicalise_bundle(b)
    assert canonicalise_bundle(b) == bytes_out
    # The canonical bytes contain the 1 MB string (approximately --
    # JSON encoding overhead is small for ASCII content).
    assert len(bytes_out) >= 1_000_000


# ---------------------------------------------------------------------------
# JSON parse limits at deserialise time
# ---------------------------------------------------------------------------


def test_truncated_json_rejected() -> None:
    """An attacker submits canonical-looking bytes that are
    half-truncated. Deserialise MUST reject with a clear error,
    not silently fill in defaults."""
    b = ReplayBundle(
        audit_id=_AUDIT_ID,
        tenant_id=_TENANT_ID,
        decision="allow",
        risk_score=0.1,
        request_envelope={"a": 1},
        timestamp_unix_ns=1_700_000_000_000_000_000,
    )
    full = canonicalise_bundle(b)
    truncated = full[: len(full) // 2]
    with pytest.raises(ValueError, match="UTF-8|JSON"):
        deserialise_bundle(truncated)
