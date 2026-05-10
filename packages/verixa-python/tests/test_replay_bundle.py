"""pytest suite for verixa_runtime.replay.bundle (CP-12.1).

Coverage strategy: pure module, all branches reachable from
behavioural fixtures. Three layers:

  1. Dataclass invariants for the three frozen records.
  2. canonicalise_bundle determinism + structural correctness
     (parses back to expected JSON object).
  3. deserialise_bundle round-trip + every reject branch
     (non-JSON, non-object, missing fields, wrong schema_version,
     None vs populated triad_review).
"""

from __future__ import annotations

import json
import uuid

import pytest

from verixa_runtime.replay import (
    BUNDLE_SCHEMA_VERSION,
    PolicyEvaluationRecord,
    ReplayBundle,
    TriadReviewRecord,
    canonicalise_bundle,
    deserialise_bundle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_AUDIT_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
_TENANT_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")


def _minimal_bundle(**overrides: object) -> ReplayBundle:
    defaults: dict[str, object] = {
        "audit_id": _AUDIT_ID,
        "tenant_id": _TENANT_ID,
        "decision": "allow",
        "risk_score": 0.1,
        "request_envelope": {"action": {"type": "tool_call"}},
        "timestamp_unix_ns": 1_700_000_000_000_000_000,
    }
    defaults.update(overrides)
    return ReplayBundle(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Layer 1: dataclass invariants
# ---------------------------------------------------------------------------


def test_policy_eval_rejects_empty_package() -> None:
    with pytest.raises(ValueError, match="package"):
        PolicyEvaluationRecord(package="", decision="pass", reason="r")


def test_policy_eval_rejects_unknown_decision() -> None:
    with pytest.raises(ValueError, match="decision"):
        PolicyEvaluationRecord(package="p", decision="maybe", reason="r")


def test_policy_eval_accepts_three_valid_decisions() -> None:
    PolicyEvaluationRecord(package="p", decision="pass", reason="")
    PolicyEvaluationRecord(package="p", decision="fail", reason="")
    PolicyEvaluationRecord(package="p", decision="abstain", reason="")


def test_triad_record_rejects_unknown_consensus_kind() -> None:
    with pytest.raises(ValueError, match="consensus_kind"):
        TriadReviewRecord(consensus_kind="confused", agreed_decision=None)


def test_triad_record_rejects_unknown_agreed_decision() -> None:
    with pytest.raises(ValueError, match="agreed_decision"):
        TriadReviewRecord(
            consensus_kind="unanimous", agreed_decision="maybe"
        )


def test_triad_record_accepts_none_agreed_decision() -> None:
    """SPLIT and INTEGRITY_FAILURE bundles have agreed_decision=None."""
    TriadReviewRecord(consensus_kind="split", agreed_decision=None)


def test_bundle_rejects_unknown_decision() -> None:
    with pytest.raises(ValueError, match="decision"):
        _minimal_bundle(decision="maybe")


def test_bundle_rejects_risk_below_zero() -> None:
    with pytest.raises(ValueError, match="risk_score"):
        _minimal_bundle(risk_score=-0.01)


def test_bundle_rejects_risk_above_one() -> None:
    with pytest.raises(ValueError, match="risk_score"):
        _minimal_bundle(risk_score=1.01)


def test_bundle_rejects_negative_timestamp() -> None:
    with pytest.raises(ValueError, match="timestamp_unix_ns"):
        _minimal_bundle(timestamp_unix_ns=-1)


def test_bundle_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        _minimal_bundle(schema_version=99)


def test_bundle_rejects_malformed_retrieved_documents() -> None:
    """retrieved_documents entries must be 2-tuples of strings."""
    with pytest.raises(ValueError, match="retrieved_documents"):
        _minimal_bundle(retrieved_documents=(("doc1",),))  # single-elem tuple


def test_bundle_rejects_non_tuple_retrieved_document() -> None:
    with pytest.raises(ValueError, match="retrieved_documents"):
        # A dict slips in instead of a tuple.
        _minimal_bundle(retrieved_documents=({"doc_id": "x"},))


def test_bundle_rejects_non_string_doc_id() -> None:
    with pytest.raises(ValueError, match="retrieved_documents"):
        _minimal_bundle(retrieved_documents=((1, "abc"),))


def test_bundle_rejects_non_string_sha256() -> None:
    with pytest.raises(ValueError, match="retrieved_documents"):
        _minimal_bundle(retrieved_documents=(("d1", 123),))


def test_bundle_accepts_minimal_inputs() -> None:
    b = _minimal_bundle()
    assert b.decision == "allow"
    assert b.schema_version == BUNDLE_SCHEMA_VERSION
    assert b.triad_review is None
    assert b.retrieved_documents == ()


# ---------------------------------------------------------------------------
# Layer 2: canonicalise_bundle determinism + structure
# ---------------------------------------------------------------------------


def test_canonicalise_is_deterministic() -> None:
    b = _minimal_bundle()
    a = canonicalise_bundle(b)
    c = canonicalise_bundle(b)
    assert a == c


def test_canonicalise_returns_utf8_bytes() -> None:
    b = _minimal_bundle()
    out = canonicalise_bundle(b)
    assert isinstance(out, bytes)
    out.decode("utf-8")  # must not raise


def test_canonicalise_keys_are_sorted() -> None:
    b = _minimal_bundle()
    parsed = json.loads(canonicalise_bundle(b))
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_canonicalise_includes_all_required_fields() -> None:
    b = _minimal_bundle()
    parsed = json.loads(canonicalise_bundle(b))
    required = {
        "schema_version", "audit_id", "tenant_id", "decision",
        "risk_score", "request_envelope", "retrieved_documents",
        "tool_io", "policy_evaluations", "triad_review",
        "timestamp_unix_ns",
    }
    assert set(parsed.keys()) == required


def test_canonicalise_with_triad_emits_nested_structure() -> None:
    """A bundle with a TriadReviewRecord canonicalises to a nested
    triad_review object, not None."""
    triad = TriadReviewRecord(
        consensus_kind="majority",
        agreed_decision="allow",
        verdicts=(
            ("reviewer_a", "allow", 0.9, "ok"),
            ("reviewer_b", "allow", 0.8, "fine"),
            ("reviewer_c", "deny", 0.7, "nope"),
        ),
        commitments=(
            ("reviewer_a", "a" * 64),
            ("reviewer_b", "b" * 64),
            ("reviewer_c", "c" * 64),
        ),
    )
    b = _minimal_bundle(triad_review=triad)
    parsed = json.loads(canonicalise_bundle(b))
    assert parsed["triad_review"] is not None
    assert parsed["triad_review"]["consensus_kind"] == "majority"
    assert len(parsed["triad_review"]["verdicts"]) == 3
    assert len(parsed["triad_review"]["commitments"]) == 3
    # Spot-check one verdict's shape.
    v0 = parsed["triad_review"]["verdicts"][0]
    assert v0["reviewer_id"] == "reviewer_a"
    assert v0["decision"] == "allow"
    assert v0["confidence"] == 0.9
    assert v0["reasoning"] == "ok"


def test_canonicalise_with_policy_evaluations() -> None:
    b = _minimal_bundle(
        policy_evaluations=(
            PolicyEvaluationRecord(
                package="verixa.fs.transfer_limit",
                decision="pass",
                reason="under limit",
            ),
            PolicyEvaluationRecord(
                package="verixa.core.workflow",
                decision="abstain",
                reason="undefined",
            ),
        )
    )
    parsed = json.loads(canonicalise_bundle(b))
    assert len(parsed["policy_evaluations"]) == 2
    assert parsed["policy_evaluations"][0]["package"] == (
        "verixa.fs.transfer_limit"
    )
    assert parsed["policy_evaluations"][1]["decision"] == "abstain"


# ---------------------------------------------------------------------------
# Layer 3: deserialise_bundle
# ---------------------------------------------------------------------------


def test_deserialise_round_trips_minimal_bundle() -> None:
    b = _minimal_bundle()
    bytes_out = canonicalise_bundle(b)
    b2 = deserialise_bundle(bytes_out)
    assert b2.audit_id == b.audit_id
    assert b2.tenant_id == b.tenant_id
    assert b2.decision == b.decision
    assert b2.risk_score == pytest.approx(b.risk_score)
    assert b2.triad_review is None
    assert b2.retrieved_documents == ()


def test_deserialise_round_trips_full_bundle() -> None:
    triad = TriadReviewRecord(
        consensus_kind="unanimous",
        agreed_decision="deny",
        verdicts=(
            ("reviewer_a", "deny", 0.95, "blocked"),
            ("reviewer_b", "deny", 0.9, "blocked"),
            ("reviewer_c", "deny", 0.92, "blocked"),
        ),
        commitments=(
            ("reviewer_a", "1" * 64),
            ("reviewer_b", "2" * 64),
            ("reviewer_c", "3" * 64),
        ),
    )
    policy_evals = (
        PolicyEvaluationRecord(
            package="verixa.fs.transfer_limit",
            decision="fail",
            reason="over limit",
        ),
    )
    b = _minimal_bundle(
        decision="deny",
        risk_score=0.85,
        retrieved_documents=(
            ("doc_001", "f" * 64),
            ("doc_002", "0" * 64),
        ),
        tool_io=({"call": "x", "response": "y"},),
        policy_evaluations=policy_evals,
        triad_review=triad,
    )
    bytes_out = canonicalise_bundle(b)
    b2 = deserialise_bundle(bytes_out)
    assert b2.decision == "deny"
    assert b2.risk_score == pytest.approx(0.85)
    assert b2.retrieved_documents == (
        ("doc_001", "f" * 64),
        ("doc_002", "0" * 64),
    )
    assert b2.tool_io == ({"call": "x", "response": "y"},)
    assert len(b2.policy_evaluations) == 1
    assert b2.policy_evaluations[0].decision == "fail"
    assert b2.triad_review is not None
    assert b2.triad_review.consensus_kind == "unanimous"
    assert b2.triad_review.agreed_decision == "deny"
    assert len(b2.triad_review.verdicts) == 3
    assert len(b2.triad_review.commitments) == 3


def test_deserialise_rejects_invalid_utf8() -> None:
    with pytest.raises(ValueError, match="UTF-8|JSON"):
        deserialise_bundle(b"\xff\xfe not valid utf-8")


def test_deserialise_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="UTF-8|JSON"):
        deserialise_bundle(b"not json at all")


def test_deserialise_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        deserialise_bundle(b"[1,2,3]")


def test_deserialise_rejects_missing_fields() -> None:
    """Drop one required field; deserialisation must complain."""
    b = _minimal_bundle()
    parsed = json.loads(canonicalise_bundle(b))
    del parsed["risk_score"]
    bad = json.dumps(parsed).encode("utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        deserialise_bundle(bad)


def test_deserialise_rejects_unknown_schema_version() -> None:
    b = _minimal_bundle()
    parsed = json.loads(canonicalise_bundle(b))
    parsed["schema_version"] = 99
    bad = json.dumps(parsed).encode("utf-8")
    with pytest.raises(ValueError, match="unsupported schema_version"):
        deserialise_bundle(bad)
