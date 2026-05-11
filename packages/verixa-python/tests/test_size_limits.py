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
  - spiffe_id capped at 512 chars (RFC norm)
  - reasoning_chain_summary capped (discovered at CP-30 RED at 189ebf4)
  - bundle.canonicalise produces deterministic output regardless of
    nesting depth (no recursion explosion in our code)
  - ReplayBundle rejects empty doc_id or empty hash in retrieved_documents
    (Phase-1 gap closed at CP-30.1 commit d5ca5da on 2026-05-11 11:54 UK;
    test_empty_doc_id_in_replay_bundle_rejected was xfail-strict between
    189ebf4 and d5ca5da, now positive)

Adversarial framing: an attacker submits "transfer 50" with a 1 MB
reasoning_chain_summary, or a 200-level nested envelope, or a 1000-
element retrieved_documents array. Defences are: caps where stored,
preservation + linear scaling where unbounded.

CP-30 RED finding (189ebf4 -> 004b104 GREEN -> d5ca5da Phase-1 gap close):
the reasoning_chain_summary cap and spiffe_id cap were not visible from
the envelope module docstring; this test file makes them executable
documentation. The empty doc_id in ReplayBundle WAS a real Phase-1 gap;
now closed by the validator fix.
"""

from __future__ import annotations

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
# Length caps on free-text fields (DEFENCE: cap, not preserve)
# ---------------------------------------------------------------------------


def test_oversized_reasoning_chain_summary_rejected() -> None:
    """100 KB of reasoning text exceeds the schema cap. The validator
    rejects with string_too_long. This is the audit-log size-bomb
    defence."""
    big = "x" * 100_000
    with pytest.raises(ValidationError, match="too_long|too long"):
        GovernContext(
            prompt_hash="a" * 64,
            model_version="m",
            reasoning_chain_summary=big,
        )


def test_oversized_spiffe_id_rejected() -> None:
    """SPIFFE IDs are capped at 512 chars (RFC norm). An attacker
    substituting a 10 KB spiffe URI is rejected at the envelope
    boundary."""
    big_spiffe = "spiffe://example/" + ("a" * 10_000)
    with pytest.raises(ValidationError, match="too_long|too long"):
        AgentIdentity(spiffe_id=big_spiffe, role="r", workflow_id=_WF_ID)


# ---------------------------------------------------------------------------
# Fixed-length fields (CANNOT inflate or deflate)
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
# Phase-1 gap NOW CLOSED: empty doc_id in ReplayBundle (CP-30.1 d5ca5da)
# ---------------------------------------------------------------------------


def test_empty_doc_id_in_replay_bundle_rejected() -> None:
    """ReplayBundle MUST reject empty doc_id strings in retrieved_documents.

    Phase-1 gap closure history:
      - CP-30 RED 189ebf4: test wrote, ReplayBundle did NOT reject empty
        doc_id; pytest reported FAILED.
      - CP-30 size-limits GREEN 004b104: test marked @xfail(strict=True)
        with Phase-1 ticket text in reason; CI ran cleanly.
      - CP-30.1 d5ca5da: ReplayBundle.__post_init__ now rejects empty
        doc_id and empty hash explicitly.
      - This commit: xfail marker removed; test now asserts the correct
        defence as a positive expectation."""
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


def test_empty_hash_in_replay_bundle_rejected() -> None:
    """And the symmetric case: empty content_sha256_hex is also
    rejected by the same validator clause (CP-30.1 d5ca5da)."""
    with pytest.raises(ValueError, match="retrieved_documents"):
        ReplayBundle(
            audit_id=_AUDIT_ID,
            tenant_id=_TENANT_ID,
            decision="allow",
            risk_score=0.1,
            request_envelope={"a": 1},
            retrieved_documents=(("doc_001", ""),),
            timestamp_unix_ns=1_700_000_000_000_000_000,
        )


# ---------------------------------------------------------------------------
# Large but valid bundle scaling
# ---------------------------------------------------------------------------


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
    must complete without OOM and produce deterministic output. The
    request_envelope is `dict[str, Any]` -- unbounded by schema so
    the validator preserves; the cap defence is at the bundle
    consumer (storage)."""
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
