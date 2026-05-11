"""pytest suite for verixa_runtime.crypto.ed25519.

Coverage discipline: 100% line + branch on the module under test.
Mix of unit tests + Hypothesis property tests.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from verixa_runtime.crypto.ed25519 import (
    PRIVATE_KEY_BYTES,
    PUBLIC_KEY_BYTES,
    SIGNATURE_BYTES,
    Ed25519KeyPair,
    Ed25519SignatureError,
    generate_keypair,
    sign,
    verify,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_constants_are_correct() -> None:
    assert PUBLIC_KEY_BYTES == 32
    assert PRIVATE_KEY_BYTES == 32
    assert SIGNATURE_BYTES == 64


# ---------------------------------------------------------------------------
# Ed25519KeyPair dataclass
# ---------------------------------------------------------------------------


def test_keypair_is_frozen() -> None:
    kp = generate_keypair()
    with pytest.raises((AttributeError, Exception)):
        kp.private_key = b"\x00" * 32  # type: ignore[misc]


def test_keypair_rejects_wrong_private_key_length() -> None:
    with pytest.raises(ValueError, match="private_key must be 32 bytes"):
        Ed25519KeyPair(private_key=b"\x00" * 16, public_key=b"\x00" * 32)


def test_keypair_rejects_wrong_public_key_length() -> None:
    with pytest.raises(ValueError, match="public_key must be 32 bytes"):
        Ed25519KeyPair(private_key=b"\x00" * 32, public_key=b"\x00" * 16)


# ---------------------------------------------------------------------------
# generate_keypair
# ---------------------------------------------------------------------------


def test_generate_keypair_produces_correct_lengths() -> None:
    kp = generate_keypair()
    assert len(kp.private_key) == PRIVATE_KEY_BYTES
    assert len(kp.public_key) == PUBLIC_KEY_BYTES


def test_generate_keypair_produces_unique_keys() -> None:
    kps = [generate_keypair() for _ in range(10)]
    private_keys = {kp.private_key for kp in kps}
    public_keys = {kp.public_key for kp in kps}
    assert len(private_keys) == 10
    assert len(public_keys) == 10


# ---------------------------------------------------------------------------
# sign — input validation
# ---------------------------------------------------------------------------


def test_sign_rejects_wrong_private_key_length() -> None:
    with pytest.raises(ValueError, match="private_key must be 32 bytes"):
        sign(b"\x00" * 16, b"hello")


def test_sign_rejects_non_bytes_message() -> None:
    kp = generate_keypair()
    with pytest.raises(TypeError, match="message must be bytes-like"):
        sign(kp.private_key, "not bytes")  # type: ignore[arg-type]


def test_sign_returns_64_byte_signature() -> None:
    kp = generate_keypair()
    sig = sign(kp.private_key, b"hello")
    assert isinstance(sig, bytes)
    assert len(sig) == SIGNATURE_BYTES


def test_sign_accepts_bytearray_message() -> None:
    kp = generate_keypair()
    sig = sign(kp.private_key, bytearray(b"bytearray-message"))
    assert len(sig) == SIGNATURE_BYTES


# ---------------------------------------------------------------------------
# verify — input validation + happy path
# ---------------------------------------------------------------------------


def test_verify_rejects_wrong_public_key_length() -> None:
    with pytest.raises(ValueError, match="public_key must be 32 bytes"):
        verify(b"\x00" * 16, b"msg", b"\x00" * 64)


def test_verify_rejects_wrong_signature_length() -> None:
    kp = generate_keypair()
    with pytest.raises(Ed25519SignatureError, match="signature must be 64"):
        verify(kp.public_key, b"msg", b"\x00" * 32)


def test_verify_rejects_non_bytes_message() -> None:
    kp = generate_keypair()
    sig = sign(kp.private_key, b"hello")
    with pytest.raises(TypeError, match="message must be bytes-like"):
        verify(kp.public_key, "hello", sig)  # type: ignore[arg-type]


def test_verify_passes_for_valid_signature() -> None:
    kp = generate_keypair()
    msg = b"audit-entry-payload"
    sig = sign(kp.private_key, msg)
    # Returns None on success
    assert verify(kp.public_key, msg, sig) is None


def test_verify_fails_for_wrong_message() -> None:
    kp = generate_keypair()
    sig = sign(kp.private_key, b"original")
    with pytest.raises(Ed25519SignatureError, match="verification failed"):
        verify(kp.public_key, b"tampered", sig)


def test_verify_fails_for_wrong_public_key() -> None:
    kp1 = generate_keypair()
    kp2 = generate_keypair()
    sig = sign(kp1.private_key, b"msg")
    with pytest.raises(Ed25519SignatureError):
        verify(kp2.public_key, b"msg", sig)


def test_verify_fails_for_corrupted_signature() -> None:
    kp = generate_keypair()
    sig = sign(kp.private_key, b"msg")
    corrupted = bytearray(sig)
    corrupted[0] ^= 0x01  # flip one bit
    with pytest.raises(Ed25519SignatureError):
        verify(kp.public_key, b"msg", bytes(corrupted))


def test_verify_accepts_bytearray_message() -> None:
    kp = generate_keypair()
    msg = b"hello"
    sig = sign(kp.private_key, msg)
    verify(kp.public_key, bytearray(msg), sig)


# ---------------------------------------------------------------------------
# Hypothesis property tests — roundtrip + tampering detection
# ---------------------------------------------------------------------------


@given(message=st.binary(min_size=0, max_size=4096))
@settings(max_examples=50, deadline=None)
def test_property_sign_verify_roundtrip(message: bytes) -> None:
    """For any message: sign(priv, m) verifies under matching pub."""
    kp = generate_keypair()
    sig = sign(kp.private_key, message)
    verify(kp.public_key, message, sig)  # must not raise


@given(
    message=st.binary(min_size=1, max_size=512),
    flip_index=st.integers(min_value=0, max_value=63),
)
@settings(max_examples=30, deadline=None)
def test_property_signature_tampering_detected(
    message: bytes, flip_index: int
) -> None:
    """Flipping any single bit in the signature must fail verification."""
    kp = generate_keypair()
    sig = sign(kp.private_key, message)
    tampered = bytearray(sig)
    tampered[flip_index] ^= 0x01
    with pytest.raises(Ed25519SignatureError):
        verify(kp.public_key, message, bytes(tampered))


@given(
    message=st.binary(min_size=1, max_size=512),
    flip_index=st.integers(min_value=0),
)
@settings(max_examples=30, deadline=None)
def test_property_message_tampering_detected(
    message: bytes, flip_index: int
) -> None:
    """Flipping any byte in the message must fail verification."""
    kp = generate_keypair()
    sig = sign(kp.private_key, message)
    if flip_index >= len(message):
        return  # nothing to flip; skip this draw
    tampered = bytearray(message)
    tampered[flip_index] ^= 0xFF
    if bytes(tampered) == message:  # vanishingly unlikely but possible if 0xFF^x==x
        return
    with pytest.raises(Ed25519SignatureError):
        verify(kp.public_key, bytes(tampered), sig)


# ---------------------------------------------------------------------------
# Public-API surface (the package exports these)
# ---------------------------------------------------------------------------


def test_package_reexports() -> None:
    from verixa_runtime import crypto

    for name in (
        "Ed25519KeyPair",
        "Ed25519SignatureError",
        "generate_keypair",
        "sign",
        "verify",
    ):
        assert hasattr(crypto, name), f"crypto.__init__ missing {name}"
