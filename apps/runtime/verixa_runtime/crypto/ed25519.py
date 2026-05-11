"""Ed25519 sign/verify primitives — audit-ledger signing.

Wraps PyNaCl (libsodium binding) for Ed25519 operations. Why PyNaCl over
`cryptography`'s Ed25519? Two reasons:

1. PyNaCl exposes raw 32-byte keys, which is the format the audit ledger
   stores (no PEM round-trips for hot-path verification).
2. PyNaCl uses libsodium under the hood; constant-time verification is
   guaranteed by the underlying library (matters for signature-oracle
   resistance in the threat model).

Public API:
  - `Ed25519KeyPair`       — frozen dataclass holding (private, public) bytes
  - `generate_keypair()`   — fresh keypair from `secrets`-grade RNG
  - `sign(private, msg)`   — returns 64-byte signature
  - `verify(public, msg, sig)` — raises Ed25519SignatureError on bad sig

Constants:
  - `PUBLIC_KEY_BYTES = 32`
  - `PRIVATE_KEY_BYTES = 32`  (seed; libsodium expands to 64 internally)
  - `SIGNATURE_BYTES = 64`
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

PUBLIC_KEY_BYTES: Final[int] = 32
PRIVATE_KEY_BYTES: Final[int] = 32
SIGNATURE_BYTES: Final[int] = 64


class Ed25519SignatureError(ValueError):
    """Raised when Ed25519 signature verification fails."""


@dataclass(frozen=True, slots=True)
class Ed25519KeyPair:
    """An Ed25519 keypair — 32-byte private seed + 32-byte public key."""

    private_key: bytes
    public_key: bytes

    def __post_init__(self) -> None:
        if len(self.private_key) != PRIVATE_KEY_BYTES:
            raise ValueError(
                f"private_key must be {PRIVATE_KEY_BYTES} bytes, "
                f"got {len(self.private_key)}"
            )
        if len(self.public_key) != PUBLIC_KEY_BYTES:
            raise ValueError(
                f"public_key must be {PUBLIC_KEY_BYTES} bytes, "
                f"got {len(self.public_key)}"
            )


def generate_keypair() -> Ed25519KeyPair:
    """Generate a fresh Ed25519 keypair from libsodium's CSPRNG."""
    signing_key = SigningKey.generate()
    return Ed25519KeyPair(
        private_key=bytes(signing_key),
        public_key=bytes(signing_key.verify_key),
    )


def sign(private_key: bytes, message: bytes) -> bytes:
    """Sign `message` with `private_key`. Returns 64-byte signature."""
    if len(private_key) != PRIVATE_KEY_BYTES:
        raise ValueError(
            f"private_key must be {PRIVATE_KEY_BYTES} bytes, "
            f"got {len(private_key)}"
        )
    if not isinstance(message, bytes | bytearray):
        raise TypeError(
            f"message must be bytes-like, got {type(message).__name__}"
        )
    signing_key = SigningKey(bytes(private_key))
    signed = signing_key.sign(bytes(message))
    return signed.signature


def verify(public_key: bytes, message: bytes, signature: bytes) -> None:
    """Verify `signature` over `message` with `public_key`.

    Returns None on success. Raises `Ed25519SignatureError` on failure.
    Never returns False (no silent-fail booleans).
    """
    if len(public_key) != PUBLIC_KEY_BYTES:
        raise ValueError(
            f"public_key must be {PUBLIC_KEY_BYTES} bytes, "
            f"got {len(public_key)}"
        )
    if len(signature) != SIGNATURE_BYTES:
        raise Ed25519SignatureError(
            f"signature must be {SIGNATURE_BYTES} bytes, "
            f"got {len(signature)}"
        )
    if not isinstance(message, bytes | bytearray):
        raise TypeError(
            f"message must be bytes-like, got {type(message).__name__}"
        )

    verify_key = VerifyKey(bytes(public_key))
    try:
        verify_key.verify(bytes(message), bytes(signature))
    except BadSignatureError as e:
        raise Ed25519SignatureError(
            "Ed25519 signature verification failed"
        ) from e
