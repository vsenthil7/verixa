"""CP-63 tests for ReplayResponse + DossierGenerateResponse + DossierGetResponse.

Extends CP-61/CP-62 test_sdk_envelopes.py with the 3 new envelopes.
Same pattern: positive case + missing required + invalid types +
forward-compat extra fields + immutability + nested-collection-type
correctness.

ReplayResponse is the most complex envelope (10 fields including 3
list-of-dict collections and 1 optional dict for triad_review); covers
the no-triad path (triad_review=None) AND the triad path (dict).

DossierGetResponse has length invariants on signature_hex (128 hex
chars = 64 bytes Ed25519 sig) and public_key_hex (64 hex chars =
32 bytes Ed25519 public key); tests pin both.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from verixa.envelopes import (
    DossierGenerateResponse,
    DossierGetResponse,
    InvalidEnvelopeError,
    ReplayResponse,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _replay_payload(**overrides) -> dict:
    payload = {
        "audit_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "decision": "allow",
        "risk_score": 0.12,
        "request_envelope": {"prompt": "approve this payment"},
        "retrieved_documents": [
            {"doc_id": "d1", "content_sha256": "abc"},
            {"doc_id": "d2", "content_sha256": "def"},
        ],
        "tool_io": [{"name": "lookup", "input": {}, "output": "ok"}],
        "policy_evaluations": [
            {"package": "fs.pii", "decision": "allow", "reason": "no pii"}
        ],
        "triad_review": None,
        "timestamp_unix_ns": 1747000000000000000,
    }
    payload.update(overrides)
    return payload


def _dossier_generate_payload(**overrides) -> dict:
    payload = {
        "dossier_id": str(uuid.uuid4()),
        "audit_id": str(uuid.uuid4()),
        "signing_key_id": "verixa-sig-dev",
        "generated_at": _now(),
    }
    payload.update(overrides)
    return payload


def _dossier_get_payload(**overrides) -> dict:
    payload = {
        "dossier_id": str(uuid.uuid4()),
        "audit_id": str(uuid.uuid4()),
        "manifest": {"summary": "ok"},
        "signature_hex": "a" * 128,
        "public_key_hex": "b" * 64,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# ReplayResponse -- positive cases
# ---------------------------------------------------------------------------


def test_replay_response_parses_no_triad_review() -> None:
    parsed = ReplayResponse.from_dict(_replay_payload())
    assert parsed.decision == "allow"
    assert parsed.risk_score == 0.12
    assert parsed.triad_review is None
    assert parsed.timestamp_unix_ns == 1747000000000000000


def test_replay_response_parses_with_triad_review() -> None:
    """When the decision escalated to triad review, triad_review is a
    dict carrying the panel's deliberation. Pass through opaquely."""
    triad = {"agreement": True, "votes": [{"model": "qwen3", "vote": "approve"}]}
    parsed = ReplayResponse.from_dict(_replay_payload(triad_review=triad))
    assert parsed.triad_review == triad


def test_replay_response_collections_are_tuples() -> None:
    """Immutability: customers cannot mutate the parsed result into
    affecting downstream SDK state."""
    parsed = ReplayResponse.from_dict(_replay_payload())
    assert isinstance(parsed.retrieved_documents, tuple)
    assert isinstance(parsed.tool_io, tuple)
    assert isinstance(parsed.policy_evaluations, tuple)


def test_replay_response_inner_dicts_pass_through_opaquely() -> None:
    """The SDK does NOT parse the inner dicts (request_envelope,
    retrieved_documents[i], tool_io[i], policy_evaluations[i]) -- they
    pass through as plain dicts so customer code can drill in or wrap
    with their own model."""
    req = {"nested": {"deeper": {"value": 42}}}
    parsed = ReplayResponse.from_dict(_replay_payload(request_envelope=req))
    assert parsed.request_envelope == req
    # Deeply nested still accessible
    assert parsed.request_envelope["nested"]["deeper"]["value"] == 42


def test_replay_response_accepts_empty_collections() -> None:
    """A decision with no retrieved docs, no tool calls, and no policy
    evaluations is unusual but valid (e.g. pure-LLM decision with no
    RAG and no firewall hits)."""
    parsed = ReplayResponse.from_dict(_replay_payload(
        retrieved_documents=[],
        tool_io=[],
        policy_evaluations=[],
    ))
    assert parsed.retrieved_documents == ()
    assert parsed.tool_io == ()
    assert parsed.policy_evaluations == ()


def test_replay_response_ignores_extra_fields() -> None:
    parsed = ReplayResponse.from_dict(_replay_payload(future_field=42))
    assert parsed.decision == "allow"


def test_replay_response_is_frozen() -> None:
    parsed = ReplayResponse.from_dict(_replay_payload())
    with pytest.raises((AttributeError, TypeError)):
        parsed.decision = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ReplayResponse -- error cases
# ---------------------------------------------------------------------------


def test_replay_response_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        ReplayResponse.from_dict(42)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    [
        "audit_id",
        "tenant_id",
        "decision",
        "risk_score",
        "request_envelope",
        "retrieved_documents",
        "tool_io",
        "policy_evaluations",
        "timestamp_unix_ns",
    ],
)
def test_replay_response_rejects_missing_required(missing_key: str) -> None:
    """triad_review is optional (the only one); all 9 others required."""
    payload = _replay_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        ReplayResponse.from_dict(payload)


def test_replay_response_omitting_triad_review_yields_none() -> None:
    """Server may omit the triad_review key entirely when not triaded
    (vs sending null); SDK accepts both."""
    payload = _replay_payload()
    del payload["triad_review"]
    parsed = ReplayResponse.from_dict(payload)
    assert parsed.triad_review is None


def test_replay_response_rejects_non_dict_request_envelope() -> None:
    payload = _replay_payload(request_envelope="not-a-dict")
    with pytest.raises(InvalidEnvelopeError, match="field request_envelope: expected dict"):
        ReplayResponse.from_dict(payload)


def test_replay_response_rejects_non_list_retrieved_documents() -> None:
    payload = _replay_payload(retrieved_documents={})
    with pytest.raises(
        InvalidEnvelopeError, match="field retrieved_documents: expected list"
    ):
        ReplayResponse.from_dict(payload)


def test_replay_response_rejects_non_dict_in_retrieved_documents() -> None:
    """Per-element validation: a non-dict inside the list MUST surface
    with the index in the field name for debuggability."""
    payload = _replay_payload(
        retrieved_documents=[{"ok": 1}, "not-a-dict", {"ok": 2}]
    )
    with pytest.raises(
        InvalidEnvelopeError, match=r"retrieved_documents\[1\]: expected dict"
    ):
        ReplayResponse.from_dict(payload)


def test_replay_response_rejects_non_dict_triad_review() -> None:
    """triad_review is Optional[dict] but if present must be a dict, not
    a string or list."""
    payload = _replay_payload(triad_review="not-a-dict")
    with pytest.raises(InvalidEnvelopeError, match="field triad_review: expected dict"):
        ReplayResponse.from_dict(payload)


def test_replay_response_rejects_bool_for_timestamp() -> None:
    payload = _replay_payload(timestamp_unix_ns=True)
    with pytest.raises(InvalidEnvelopeError, match="field timestamp_unix_ns: expected int"):
        ReplayResponse.from_dict(payload)


def test_replay_response_rejects_invalid_uuid() -> None:
    payload = _replay_payload(audit_id="not-a-uuid")
    with pytest.raises(InvalidEnvelopeError, match="not a valid UUID"):
        ReplayResponse.from_dict(payload)


# ---------------------------------------------------------------------------
# DossierGenerateResponse
# ---------------------------------------------------------------------------


def test_dossier_generate_response_parses() -> None:
    parsed = DossierGenerateResponse.from_dict(_dossier_generate_payload())
    assert parsed.signing_key_id == "verixa-sig-dev"
    assert isinstance(parsed.dossier_id, uuid.UUID)
    assert isinstance(parsed.audit_id, uuid.UUID)
    assert isinstance(parsed.generated_at, datetime)


def test_dossier_generate_response_ignores_extra_fields() -> None:
    parsed = DossierGenerateResponse.from_dict(
        _dossier_generate_payload(future_field=42)
    )
    assert parsed.signing_key_id == "verixa-sig-dev"


def test_dossier_generate_response_is_frozen() -> None:
    parsed = DossierGenerateResponse.from_dict(_dossier_generate_payload())
    with pytest.raises((AttributeError, TypeError)):
        parsed.signing_key_id = "mutated"  # type: ignore[misc]


def test_dossier_generate_response_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        DossierGenerateResponse.from_dict([])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    ["dossier_id", "audit_id", "signing_key_id", "generated_at"],
)
def test_dossier_generate_response_rejects_missing_required(missing_key: str) -> None:
    payload = _dossier_generate_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        DossierGenerateResponse.from_dict(payload)


def test_dossier_generate_response_rejects_non_string_signing_key_id() -> None:
    payload = _dossier_generate_payload(signing_key_id=42)
    with pytest.raises(InvalidEnvelopeError, match="field signing_key_id"):
        DossierGenerateResponse.from_dict(payload)


# ---------------------------------------------------------------------------
# DossierGetResponse
# ---------------------------------------------------------------------------


def test_dossier_get_response_parses() -> None:
    parsed = DossierGetResponse.from_dict(_dossier_get_payload())
    assert parsed.manifest == {"summary": "ok"}
    assert len(parsed.signature_hex) == 128
    assert len(parsed.public_key_hex) == 64


def test_dossier_get_response_pins_signature_length_128_hex() -> None:
    """Ed25519 signature is 64 bytes = 128 hex chars. Wrong length is a
    server bug + must be loud."""
    for bad_len in (127, 129, 0, 64):
        payload = _dossier_get_payload(signature_hex="a" * bad_len)
        with pytest.raises(
            InvalidEnvelopeError, match="signature_hex: expected 128 hex"
        ):
            DossierGetResponse.from_dict(payload)


def test_dossier_get_response_pins_public_key_length_64_hex() -> None:
    """Ed25519 public key is 32 bytes = 64 hex chars."""
    for bad_len in (63, 65, 0, 128):
        payload = _dossier_get_payload(public_key_hex="b" * bad_len)
        with pytest.raises(
            InvalidEnvelopeError, match="public_key_hex: expected 64 hex"
        ):
            DossierGetResponse.from_dict(payload)


def test_dossier_get_response_rejects_non_dict_manifest() -> None:
    payload = _dossier_get_payload(manifest="not-a-dict")
    with pytest.raises(InvalidEnvelopeError, match="field manifest: expected dict"):
        DossierGetResponse.from_dict(payload)


def test_dossier_get_response_ignores_extra_fields() -> None:
    parsed = DossierGetResponse.from_dict(_dossier_get_payload(future_field=42))
    assert parsed.manifest == {"summary": "ok"}


def test_dossier_get_response_is_frozen() -> None:
    parsed = DossierGetResponse.from_dict(_dossier_get_payload())
    with pytest.raises((AttributeError, TypeError)):
        parsed.signature_hex = "mutated"  # type: ignore[misc]


def test_dossier_get_response_rejects_non_dict() -> None:
    with pytest.raises(InvalidEnvelopeError, match="expected dict"):
        DossierGetResponse.from_dict("oops")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    ["dossier_id", "audit_id", "manifest", "signature_hex", "public_key_hex"],
)
def test_dossier_get_response_rejects_missing_required(missing_key: str) -> None:
    payload = _dossier_get_payload()
    del payload[missing_key]
    with pytest.raises(InvalidEnvelopeError, match=f"field {missing_key}"):
        DossierGetResponse.from_dict(payload)


# ---------------------------------------------------------------------------
# Top-level re-export
# ---------------------------------------------------------------------------


def test_replay_and_dossier_envelopes_reexported_from_top_level() -> None:
    import verixa

    for name in (
        "ReplayResponse",
        "DossierGenerateResponse",
        "DossierGetResponse",
    ):
        assert name in verixa.__all__, f"{name} missing from verixa.__all__"
        assert hasattr(verixa, name), f"{name} not importable from verixa"
