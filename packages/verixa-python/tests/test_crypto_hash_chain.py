"""pytest suite for verixa_runtime.crypto.hash_chain.

Coverage discipline: 100% line + branch on the module under test.
Mix of unit tests + Hypothesis property tests for chain integrity.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from verixa_runtime.crypto.hash_chain import (
    GENESIS_PREFIX,
    SHA256_BYTES,
    HashChainBrokenError,
    HashChainEntry,
    compute_genesis_prev,
    compute_self_hash,
    verify_chain,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    seq: int,
    prev: bytes,
    *,
    workflow_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    decision: str = "allow",
    risk_score: Decimal = Decimal("0.500"),
) -> HashChainEntry:
    return HashChainEntry(
        sequence_number=seq,
        event_time=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC),
        workflow_id=workflow_id or uuid.UUID("11111111-1111-1111-1111-111111111111"),
        agent_id=agent_id or uuid.UUID("22222222-2222-2222-2222-222222222222"),
        action_type="tool_call",
        decision=decision,
        risk_score=risk_score,
        snapshot_hash=hashlib.sha256(f"snap-{seq}".encode()).digest(),
        hash_chain_prev=prev,
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_constants_are_correct() -> None:
    assert GENESIS_PREFIX == b"verixa-genesis-"
    assert SHA256_BYTES == 32


# ---------------------------------------------------------------------------
# HashChainEntry validation
# ---------------------------------------------------------------------------


def test_entry_rejects_negative_sequence_number() -> None:
    with pytest.raises(ValueError, match="sequence_number must be non-negative"):
        HashChainEntry(
            sequence_number=-1,
            event_time=datetime.now(tz=UTC),
            workflow_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=b"\x00" * 32,
            hash_chain_prev=b"\x00" * 32,
        )


def test_entry_rejects_wrong_snapshot_hash_length() -> None:
    with pytest.raises(ValueError, match="snapshot_hash must be 32 bytes"):
        HashChainEntry(
            sequence_number=0,
            event_time=datetime.now(tz=UTC),
            workflow_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=b"\x00" * 16,
            hash_chain_prev=b"\x00" * 32,
        )


def test_entry_rejects_wrong_prev_hash_length() -> None:
    with pytest.raises(ValueError, match="hash_chain_prev must be 32 bytes"):
        HashChainEntry(
            sequence_number=0,
            event_time=datetime.now(tz=UTC),
            workflow_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            action_type="x",
            decision="allow",
            risk_score=Decimal("0.5"),
            snapshot_hash=b"\x00" * 32,
            hash_chain_prev=b"\x00" * 16,
        )


def test_entry_is_frozen() -> None:
    e = _make_entry(0, b"\x00" * 32)
    with pytest.raises((AttributeError, Exception)):
        e.sequence_number = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# compute_genesis_prev
# ---------------------------------------------------------------------------


def test_genesis_prev_returns_32_bytes() -> None:
    digest = compute_genesis_prev(uuid.UUID("00000000-0000-0000-0000-000000000001"))
    assert len(digest) == SHA256_BYTES


def test_genesis_prev_is_deterministic() -> None:
    tid = uuid.UUID("12345678-1234-1234-1234-123456789012")
    assert compute_genesis_prev(tid) == compute_genesis_prev(tid)


def test_genesis_prev_differs_per_tenant() -> None:
    a = compute_genesis_prev(uuid.UUID("00000000-0000-0000-0000-000000000001"))
    b = compute_genesis_prev(uuid.UUID("00000000-0000-0000-0000-000000000002"))
    assert a != b


def test_genesis_prev_matches_canonical_definition() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    expected = hashlib.sha256(GENESIS_PREFIX + tid.bytes).digest()
    assert compute_genesis_prev(tid) == expected


def test_genesis_prev_rejects_non_uuid() -> None:
    with pytest.raises(TypeError, match="tenant_id must be uuid.UUID"):
        compute_genesis_prev("not-a-uuid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compute_self_hash
# ---------------------------------------------------------------------------


def test_self_hash_is_32_bytes() -> None:
    e = _make_entry(0, b"\x00" * 32)
    assert len(compute_self_hash(e)) == SHA256_BYTES


def test_self_hash_is_deterministic() -> None:
    e = _make_entry(0, b"\x00" * 32)
    assert compute_self_hash(e) == compute_self_hash(e)


def test_self_hash_differs_when_decision_changes() -> None:
    e1 = _make_entry(0, b"\x00" * 32, decision="allow")
    e2 = _make_entry(0, b"\x00" * 32, decision="deny")
    assert compute_self_hash(e1) != compute_self_hash(e2)


def test_self_hash_differs_when_risk_changes() -> None:
    e1 = _make_entry(0, b"\x00" * 32, risk_score=Decimal("0.100"))
    e2 = _make_entry(0, b"\x00" * 32, risk_score=Decimal("0.900"))
    assert compute_self_hash(e1) != compute_self_hash(e2)


# ---------------------------------------------------------------------------
# verify_chain — happy path
# ---------------------------------------------------------------------------


def test_verify_empty_chain_is_vacuously_consistent() -> None:
    verify_chain([], [], uuid.uuid4())  # must not raise


def test_verify_single_entry_chain_passes() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    prev = compute_genesis_prev(tid)
    e = _make_entry(0, prev)
    expected = [compute_self_hash(e)]
    verify_chain([e], expected, tid)  # must not raise


def test_verify_three_entry_chain_passes() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    chain: list[HashChainEntry] = []
    selves: list[bytes] = []
    prev = compute_genesis_prev(tid)
    for seq in range(3):
        e = _make_entry(seq, prev)
        h = compute_self_hash(e)
        chain.append(e)
        selves.append(h)
        prev = h
    verify_chain(chain, selves, tid)  # must not raise


# ---------------------------------------------------------------------------
# verify_chain — failure paths
# ---------------------------------------------------------------------------


def test_verify_detects_length_mismatch() -> None:
    with pytest.raises(HashChainBrokenError, match="length mismatch"):
        verify_chain([_make_entry(0, b"\x00" * 32)], [], uuid.uuid4())


def test_verify_detects_sequence_gap() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    prev = compute_genesis_prev(tid)
    # First entry has wrong sequence_number (1 instead of 0)
    e = _make_entry(1, prev)
    with pytest.raises(HashChainBrokenError, match="sequence gap"):
        verify_chain([e], [compute_self_hash(e)], tid)


def test_verify_detects_wrong_prev_hash() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    # Entry claims a wrong genesis_prev
    e = _make_entry(0, b"\xff" * 32)
    with pytest.raises(HashChainBrokenError, match="prev-hash mismatch"):
        verify_chain([e], [compute_self_hash(e)], tid)


def test_verify_detects_tampered_self_hash() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    prev = compute_genesis_prev(tid)
    e = _make_entry(0, prev)
    actual = compute_self_hash(e)
    tampered = bytearray(actual)
    tampered[0] ^= 0xFF
    with pytest.raises(HashChainBrokenError, match="self-hash mismatch"):
        verify_chain([e], [bytes(tampered)], tid)


def test_verify_detects_chain_split_in_middle() -> None:
    """If entry 1's hash_chain_prev != entry 0's self hash, the chain is broken."""
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    prev0 = compute_genesis_prev(tid)
    e0 = _make_entry(0, prev0)
    h0 = compute_self_hash(e0)
    # e1 claims a wrong prev (not h0)
    e1 = _make_entry(1, b"\xaa" * 32)
    h1 = compute_self_hash(e1)
    with pytest.raises(HashChainBrokenError, match="prev-hash mismatch"):
        verify_chain([e0, e1], [h0, h1], tid)


# ---------------------------------------------------------------------------
# Hypothesis property tests
# ---------------------------------------------------------------------------


@given(seq=st.integers(min_value=0, max_value=1_000_000))
@settings(max_examples=30, deadline=None)
def test_property_self_hash_deterministic_in_seq(seq: int) -> None:
    e = _make_entry(seq, b"\x00" * 32)
    assert compute_self_hash(e) == compute_self_hash(e)


@given(
    chain_length=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=15, deadline=None)
def test_property_well_formed_chain_verifies(chain_length: int) -> None:
    """Building a chain canonically and verifying it must always succeed."""
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    prev = compute_genesis_prev(tid)
    chain: list[HashChainEntry] = []
    selves: list[bytes] = []
    for seq in range(chain_length):
        e = _make_entry(seq, prev)
        h = compute_self_hash(e)
        chain.append(e)
        selves.append(h)
        prev = h
    verify_chain(chain, selves, tid)


@given(
    chain_length=st.integers(min_value=2, max_value=10),
    tamper_index=st.integers(min_value=0, max_value=9),
)
@settings(max_examples=15, deadline=None)
def test_property_any_self_hash_tamper_detected(
    chain_length: int, tamper_index: int
) -> None:
    """Tampering with any stored hash_chain_self must trip verify_chain."""
    if tamper_index >= chain_length:
        return  # skip out-of-range draws
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    prev = compute_genesis_prev(tid)
    chain: list[HashChainEntry] = []
    selves: list[bytes] = []
    for seq in range(chain_length):
        e = _make_entry(seq, prev)
        h = compute_self_hash(e)
        chain.append(e)
        selves.append(h)
        prev = h
    tampered = bytearray(selves[tamper_index])
    tampered[0] ^= 0x01
    selves[tamper_index] = bytes(tampered)
    with pytest.raises(HashChainBrokenError):
        verify_chain(chain, selves, tid)


# ---------------------------------------------------------------------------
# Public-API surface
# ---------------------------------------------------------------------------


def test_package_reexports() -> None:
    from verixa_runtime import crypto

    for name in (
        "HashChainBrokenError",
        "HashChainEntry",
        "compute_genesis_prev",
        "compute_self_hash",
        "verify_chain",
    ):
        assert hasattr(crypto, name), f"crypto package missing {name}"
