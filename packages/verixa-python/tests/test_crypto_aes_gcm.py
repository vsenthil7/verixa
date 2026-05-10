"""pytest suite for verixa_runtime.crypto.aes_gcm.

100% line + branch coverage. Hypothesis property tests cover the
encrypt/decrypt roundtrip and tampering detection.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from verixa_runtime.crypto.aes_gcm import (
    KEY_BYTES,
    NONCE_BYTES,
    TAG_BYTES,
    AesGcmCiphertext,
    AesGcmDecryptionError,
    AesGcmKey,
    decrypt,
    encrypt,
    generate_key,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_constants() -> None:
    assert KEY_BYTES == 32
    assert NONCE_BYTES == 12
    assert TAG_BYTES == 16


# ---------------------------------------------------------------------------
# AesGcmKey
# ---------------------------------------------------------------------------


def test_key_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match=r"key must be 32 bytes"):
        AesGcmKey(key=b"\x00" * 16)


def test_key_is_frozen() -> None:
    k = generate_key()
    with pytest.raises((AttributeError, Exception)):
        k.key = b"\x00" * 32  # type: ignore[misc]


def test_generate_key_produces_correct_length() -> None:
    k = generate_key()
    assert len(k.key) == KEY_BYTES


def test_generate_key_produces_unique_keys() -> None:
    keys = {generate_key().key for _ in range(20)}
    assert len(keys) == 20


# ---------------------------------------------------------------------------
# AesGcmCiphertext
# ---------------------------------------------------------------------------


def test_ciphertext_rejects_wrong_nonce_length() -> None:
    with pytest.raises(ValueError, match="nonce must be 12 bytes"):
        AesGcmCiphertext(
            nonce=b"\x00" * 8,
            ciphertext=b"\x00" * 32,
            associated_data=b"",
        )


def test_ciphertext_rejects_too_short_ciphertext() -> None:
    with pytest.raises(ValueError, match="at least 16 bytes"):
        AesGcmCiphertext(
            nonce=b"\x00" * 12,
            ciphertext=b"\x00" * 8,
            associated_data=b"",
        )


# ---------------------------------------------------------------------------
# encrypt — input validation
# ---------------------------------------------------------------------------


def test_encrypt_rejects_non_bytes_plaintext() -> None:
    k = generate_key()
    with pytest.raises(TypeError, match="plaintext must be bytes-like"):
        encrypt(k, "hello", b"")  # type: ignore[arg-type]


def test_encrypt_rejects_non_bytes_associated_data() -> None:
    k = generate_key()
    with pytest.raises(TypeError, match="associated_data must be bytes-like"):
        encrypt(k, b"hello", "ad")  # type: ignore[arg-type]


def test_encrypt_accepts_bytearray_plaintext() -> None:
    k = generate_key()
    ct = encrypt(k, bytearray(b"hello"), b"ad")
    assert isinstance(ct, AesGcmCiphertext)


def test_encrypt_accepts_bytearray_associated_data() -> None:
    k = generate_key()
    ct = encrypt(k, b"hello", bytearray(b"ad"))
    assert ct.associated_data == b"ad"


def test_encrypt_returns_correct_lengths() -> None:
    k = generate_key()
    plaintext = b"verixa-replay-bundle"
    ct = encrypt(k, plaintext, b"audit-id-x")
    assert len(ct.nonce) == NONCE_BYTES
    assert len(ct.ciphertext) == len(plaintext) + TAG_BYTES
    assert ct.associated_data == b"audit-id-x"


def test_encrypt_uses_fresh_nonce_each_call() -> None:
    k = generate_key()
    a = encrypt(k, b"x", b"")
    b = encrypt(k, b"x", b"")
    assert a.nonce != b.nonce
    assert a.ciphertext != b.ciphertext


# ---------------------------------------------------------------------------
# decrypt — happy path
# ---------------------------------------------------------------------------


def test_decrypt_roundtrip() -> None:
    k = generate_key()
    plaintext = b"some-plaintext-blob"
    ct = encrypt(k, plaintext, b"associated")
    assert decrypt(k, ct) == plaintext


def test_decrypt_empty_plaintext() -> None:
    k = generate_key()
    ct = encrypt(k, b"", b"ad")
    assert decrypt(k, ct) == b""


# ---------------------------------------------------------------------------
# decrypt — failure paths
# ---------------------------------------------------------------------------


def test_decrypt_fails_on_wrong_key() -> None:
    k1 = generate_key()
    k2 = generate_key()
    ct = encrypt(k1, b"secret", b"ad")
    with pytest.raises(AesGcmDecryptionError, match="auth tag mismatch"):
        decrypt(k2, ct)


def test_decrypt_fails_on_tampered_ciphertext() -> None:
    k = generate_key()
    ct = encrypt(k, b"secret", b"ad")
    tampered = bytearray(ct.ciphertext)
    tampered[0] ^= 0x01
    with pytest.raises(AesGcmDecryptionError):
        decrypt(
            k,
            AesGcmCiphertext(
                nonce=ct.nonce,
                ciphertext=bytes(tampered),
                associated_data=ct.associated_data,
            ),
        )


def test_decrypt_fails_on_tampered_nonce() -> None:
    k = generate_key()
    ct = encrypt(k, b"secret", b"ad")
    tampered = bytearray(ct.nonce)
    tampered[0] ^= 0x01
    with pytest.raises(AesGcmDecryptionError):
        decrypt(
            k,
            AesGcmCiphertext(
                nonce=bytes(tampered),
                ciphertext=ct.ciphertext,
                associated_data=ct.associated_data,
            ),
        )


def test_decrypt_fails_on_tampered_associated_data() -> None:
    k = generate_key()
    ct = encrypt(k, b"secret", b"original-ad")
    with pytest.raises(AesGcmDecryptionError):
        decrypt(
            k,
            AesGcmCiphertext(
                nonce=ct.nonce,
                ciphertext=ct.ciphertext,
                associated_data=b"different-ad",
            ),
        )


# ---------------------------------------------------------------------------
# Hypothesis property tests
# ---------------------------------------------------------------------------


@given(
    plaintext=st.binary(min_size=0, max_size=2048),
    associated_data=st.binary(min_size=0, max_size=256),
)
@settings(max_examples=30, deadline=None)
def test_property_roundtrip(plaintext: bytes, associated_data: bytes) -> None:
    k = generate_key()
    ct = encrypt(k, plaintext, associated_data)
    assert decrypt(k, ct) == plaintext


@given(
    plaintext=st.binary(min_size=1, max_size=512),
    flip_byte=st.integers(min_value=0),
)
@settings(max_examples=30, deadline=None)
def test_property_ciphertext_tamper_detected(
    plaintext: bytes, flip_byte: int
) -> None:
    k = generate_key()
    ct = encrypt(k, plaintext, b"ad")
    if flip_byte >= len(ct.ciphertext):
        return
    tampered = bytearray(ct.ciphertext)
    tampered[flip_byte] ^= 0xFF
    if bytes(tampered) == ct.ciphertext:
        return
    with pytest.raises(AesGcmDecryptionError):
        decrypt(
            k,
            AesGcmCiphertext(
                nonce=ct.nonce,
                ciphertext=bytes(tampered),
                associated_data=ct.associated_data,
            ),
        )


# ---------------------------------------------------------------------------
# Public-API surface
# ---------------------------------------------------------------------------


def test_package_reexports() -> None:
    from verixa_runtime import crypto

    for name in (
        "AesGcmKey",
        "AesGcmCiphertext",
        "AesGcmDecryptionError",
        "encrypt",
        "decrypt",
        "generate_key",
    ):
        assert hasattr(crypto, name), f"crypto package missing {name}"
