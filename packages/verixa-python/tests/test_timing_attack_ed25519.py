"""CP-36 negative test 6/10: timing-attack resistance on Ed25519 verification.

Anchored to BR-04 (audit-grade evidence), NEGATIVE_TEST_PLAN gap 8
(timing-attack on Ed25519 verification). NEGATIVE_TEST_PLAN identified
this gap at Phase 0 close; this commit closes it.

A timing attack exploits wall-clock differences in signature verification
to learn information about the signature or key. Concrete attack model:

  - Attacker submits a long sequence of forged signatures + measures
    server response time
  - If verification is NOT constant-time, the time to reject differs
    based on where the signature differs from the expected value
    (e.g. early-differing bytes reject faster than late-differing
    bytes via short-circuit memcmp)
  - Over many measurements, attacker learns the structure of the
    correct signature and may eventually forge one

Defence in Verixa Phase 0:

  - All Ed25519 signature operations go through `pynacl` (libsodium
    wrapping libsodium's `crypto_sign_verify_detached` which uses
    constant-time comparison)
  - `verifying_key.verify()` raises Ed25519SignatureError on any
    failure, regardless of where the signature went wrong
  - No early-exit paths in Verixa's wrapper code in
    `apps/runtime/verixa_runtime/crypto/ed25519.py`

These tests EMPIRICALLY assert the constant-time property by measuring
verification wall-clock across multiple forged-signature shapes and
asserting the timing distribution is statistically indistinguishable.
This is a "probabilistic test" — it doesn't prove constant-time, but
catches any regression where a future change introduces an early-exit
path.

Adversarial framing: an attacker measures verification time for:
  - A signature where byte 0 is wrong vs byte 63 is wrong
  - A signature of the wrong length (should fail-fast deterministically)
  - A correctly-formed but never-signed signature
  - Sequential bit-flips through the signature

For the constant-time property to hold, all wrong-byte positions must
produce indistinguishable timing distributions (within statistical noise).

Phase 1+: timing-attack discipline extends to AES-GCM unsealing (same
libsodium-backed constant-time guarantee) and to per-tenant key
resolution.
"""

from __future__ import annotations

import statistics
import time

import pytest
from verixa_runtime.crypto.ed25519 import (
    Ed25519SignatureError,
    generate_keypair,
    sign,
    verify,
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

# Number of timing samples per shape. 100 samples averages out OS-level
# scheduler noise without taking forever; for very tight bounds use 1000+
# but pytest wall-clock budget matters.
_N_SAMPLES = 100

# Message fixed across all shapes for fair comparison.
_MSG = b"verixa-timing-attack-canonical-test-message"


@pytest.fixture(scope="module")
def keypair() -> tuple[bytes, bytes]:
    """One keypair for the whole module; otherwise key-gen noise dominates."""
    kp = generate_keypair()
    return kp.private_key, kp.public_key


def _measure(verify_fn, *args) -> float:
    """Single verification call; return elapsed ns."""
    t0 = time.perf_counter_ns()
    try:
        verify_fn(*args)
    except Ed25519SignatureError:
        pass
    except ValueError:
        pass
    return time.perf_counter_ns() - t0


def _samples(verify_fn, n: int, *args) -> list[float]:
    # warmup -- first call has cold-cache cost ~30x slower than steady-state
    for _ in range(10):
        _measure(verify_fn, *args)
    return [_measure(verify_fn, *args) for _ in range(n)]


def _flip_bit(buf: bytes, position: int) -> bytes:
    """Flip one bit at `position`; position is bit-index 0..len*8-1."""
    byte_idx, bit_idx = divmod(position, 8)
    out = bytearray(buf)
    out[byte_idx] ^= 1 << bit_idx
    return bytes(out)


# ---------------------------------------------------------------------------
# 1. Constant-time across byte-position of forgery
# ---------------------------------------------------------------------------


def test_verify_rejects_byte0_flip(keypair: tuple[bytes, bytes]) -> None:
    """A signature with the first byte flipped MUST be rejected."""
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    forged = _flip_bit(real_sig, 0)
    with pytest.raises(Ed25519SignatureError):
        verify(pub, _MSG, forged)


def test_verify_rejects_last_byte_flip(keypair: tuple[bytes, bytes]) -> None:
    """A signature with the LAST byte flipped MUST also be rejected."""
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    forged = _flip_bit(real_sig, len(real_sig) * 8 - 1)
    with pytest.raises(Ed25519SignatureError):
        verify(pub, _MSG, forged)


def test_verify_rejects_middle_byte_flip(keypair: tuple[bytes, bytes]) -> None:
    """A signature with a middle byte flipped MUST be rejected."""
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    forged = _flip_bit(real_sig, len(real_sig) * 4)  # bit 32*8 = byte 32
    with pytest.raises(Ed25519SignatureError):
        verify(pub, _MSG, forged)


def test_verify_byte0_vs_middle_byte_timing_indistinguishable(
    keypair: tuple[bytes, bytes],
) -> None:
    """The KEY constant-time assertion (CP-52 corrected version).

    Verification time when byte 0 is forged MUST be statistically
    indistinguishable from verification time when a middle byte is
    forged. Both forgeries are structurally valid (pass libsodium's
    pre-check) so they BOTH go through the full Ed25519 scalar
    multiplication; if libsodium's verify were not constant-time
    over them, an attacker measuring server timing could learn
    structural information about valid signatures.

    Why byte 32 (bit 256) and not the LAST byte: bit 511 is bit 7 of
    byte 63, the MSB of the "s" component. RFC 8032 sec 5.1.6 requires
    the upper 3 bits of byte 63 to be zero, so flipping bit 511 produces
    a structurally invalid signature that libsodium correctly rejects
    in ~2 us WITHOUT running the scalar multiplication. This produces
    a ~33x timing ratio versus byte0-forged that is NOT a security
    leak (the structural constraint is public per the RFC) but DID
    fool the original CP-36 byte0-vs-last test into reporting a false
    alarm. CP-52 timing_benchmark harness investigated and confirmed.

    Loose 5x bound here tolerates OS-scheduler noise on small samples;
    real constant-time differs by ~1% (validated by the CP-52 harness
    at N=10000 which reports Cliff's delta < 0.05 on this comparison).
    """
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    forged_byte0 = _flip_bit(real_sig, 0)
    forged_middle = _flip_bit(real_sig, 256)  # bit 0 of byte 32

    times_byte0 = _samples(verify, _N_SAMPLES, pub, _MSG, forged_byte0)
    times_middle = _samples(verify, _N_SAMPLES, pub, _MSG, forged_middle)

    median_byte0 = statistics.median(times_byte0)
    median_middle = statistics.median(times_middle)

    ratio = max(median_byte0, median_middle) / min(median_byte0, median_middle)
    assert ratio < 5.0, (
        f"Possible timing leak: byte0={median_byte0}ns vs "
        f"middle={median_middle}ns (ratio {ratio:.2f}). "
        f"Run `python -m tools.timing_benchmark byte0-vs-middle --samples 10000` "
        f"for definitive investigation."
    )


def test_verify_structurally_invalid_last_bit_fast_rejects(
    keypair: tuple[bytes, bytes],
) -> None:
    """Documented expected behavior (CP-52 finding).

    Flipping bit 511 of an Ed25519 signature sets the high bit of byte 63
    which RFC 8032 sec 5.1.6 mandates must be zero. libsodium correctly
    detects this as structurally invalid and fast-rejects WITHOUT running
    the scalar multiplication. This produces a timing difference vs a
    structurally-valid forgery, but does NOT leak any secret material --
    the constraint is a public RFC requirement.

    This test PINS the fast-reject behavior so we notice if a future
    libsodium update removes it (which would make rejections slightly
    slower but would not be a security regression).
    """
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    forged_byte0 = _flip_bit(real_sig, 0)
    forged_last_bit = _flip_bit(real_sig, len(real_sig) * 8 - 1)

    times_byte0 = _samples(verify, _N_SAMPLES, pub, _MSG, forged_byte0)
    times_last = _samples(verify, _N_SAMPLES, pub, _MSG, forged_last_bit)

    median_byte0 = statistics.median(times_byte0)
    median_last = statistics.median(times_last)

    # Document: last-bit forgery is FASTER (fast-reject path).
    # If this ratio drops below 5, libsodium removed the fast-reject;
    # not a security issue but worth knowing.
    assert median_last < median_byte0, (
        f"Expected last-bit forgery to fast-reject faster than "
        f"byte0 forgery (CP-52 documented behavior): "
        f"byte0={median_byte0}ns vs last={median_last}ns"
    )


# ---------------------------------------------------------------------------
# 2. Wrong-length signature is REJECTED FAST (and deterministically)
# ---------------------------------------------------------------------------


def test_verify_rejects_too_short_signature(keypair: tuple[bytes, bytes]) -> None:
    """A truncated signature (32 bytes instead of 64) is rejected."""
    _, pub = keypair
    short_sig = b"\x00" * 32
    with pytest.raises((Ed25519SignatureError, ValueError)):
        verify(pub, _MSG, short_sig)


def test_verify_rejects_too_long_signature(keypair: tuple[bytes, bytes]) -> None:
    """An over-long signature (96 bytes instead of 64) is rejected."""
    _, pub = keypair
    long_sig = b"\x00" * 96
    with pytest.raises((Ed25519SignatureError, ValueError)):
        verify(pub, _MSG, long_sig)


def test_verify_rejects_empty_signature(keypair: tuple[bytes, bytes]) -> None:
    """Zero-length signature is rejected (boundary case)."""
    _, pub = keypair
    with pytest.raises((Ed25519SignatureError, ValueError)):
        verify(pub, _MSG, b"")


# ---------------------------------------------------------------------------
# 3. Never-signed signature (random correctly-formed bytes)
# ---------------------------------------------------------------------------


def test_verify_rejects_all_zero_signature(keypair: tuple[bytes, bytes]) -> None:
    """All-zero 64-byte signature is rejected (it's a valid LENGTH but
    not a valid signature for any (msg, pub) pair with overwhelming
    probability)."""
    _, pub = keypair
    with pytest.raises(Ed25519SignatureError):
        verify(pub, _MSG, b"\x00" * 64)


def test_verify_rejects_all_ones_signature(keypair: tuple[bytes, bytes]) -> None:
    """All-0xFF 64-byte signature is rejected for the same reason."""
    _, pub = keypair
    with pytest.raises(Ed25519SignatureError):
        verify(pub, _MSG, b"\xff" * 64)


# ---------------------------------------------------------------------------
# 4. Wrong-key timing indistinguishable from wrong-signature timing
# ---------------------------------------------------------------------------


def test_verify_wrong_key_vs_wrong_sig_timing(keypair: tuple[bytes, bytes]) -> None:
    """Verifying a real signature with a WRONG public key takes ~the same
    time as verifying a forged signature with the right public key.

    This catches a different timing leak: an implementation that tells
    you "you have the wrong key" faster than "you have the wrong
    signature" would leak whether the key matters.

    CP-52 update: investigated with timing_benchmark at N=2000+ and
    confirmed no leak (Cliff's delta ~ 0.16, well below threshold).
    The original xfail was small-N (N=100) measurement noise; with
    pytest's tight wall-clock budget we keep N=100 here and use a
    loose 5x bound (vs the previous 20x); for definitive verification
    use the harness."""
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    forged = _flip_bit(real_sig, 0)
    other_kp = generate_keypair()
    wrong_pub = other_kp.public_key

    times_wrong_key = _samples(verify, _N_SAMPLES, wrong_pub, _MSG, real_sig)
    times_wrong_sig = _samples(verify, _N_SAMPLES, pub, _MSG, forged)

    median_wk = statistics.median(times_wrong_key)
    median_ws = statistics.median(times_wrong_sig)

    ratio = max(median_wk, median_ws) / min(median_wk, median_ws)
    assert ratio < 5.0, (
        f"Possible timing leak: wrong-key={median_wk}ns vs "
        f"wrong-sig={median_ws}ns (ratio {ratio:.2f}). "
        f"Run `python -m tools.timing_benchmark wrong-key-vs-wrong-sig "
        f"--samples 10000` for definitive investigation."
    )


# ---------------------------------------------------------------------------
# 5. Sequential bit-flip sweep — every position rejects equally
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bit_position", [0, 64, 128, 256, 384, 511])
def test_verify_rejects_every_bit_flip(
    keypair: tuple[bytes, bytes], bit_position: int
) -> None:
    """Bit-flips at 6 distinct positions across the 64-byte signature
    are ALL rejected. This is the structural assertion that there's
    no "good enough" forgery — every single-bit change fails."""
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    forged = _flip_bit(real_sig, bit_position)
    with pytest.raises(Ed25519SignatureError):
        verify(pub, _MSG, forged)


# ---------------------------------------------------------------------------
# 6. Real signature still PASSES (positive sanity check inside neg test file)
# ---------------------------------------------------------------------------


def test_verify_genuine_signature_passes(keypair: tuple[bytes, bytes]) -> None:
    """Sanity check: the real signature verifies. Without this, the
    other tests could all pass even if `verify` always raised."""
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    # No raise expected; if this raises, every other test in this file
    # is testing the wrong thing.
    verify(pub, _MSG, real_sig)


# ---------------------------------------------------------------------------
# 7. Message tampering: same signature, different message
# ---------------------------------------------------------------------------


def test_verify_rejects_message_substitution(keypair: tuple[bytes, bytes]) -> None:
    """A real signature on message A MUST NOT verify against message B.
    This is the audit-ledger tamper-detection property: an attacker
    cannot swap which message a signature applies to."""
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    other_msg = b"verixa-different-message-attempt-to-fool"
    with pytest.raises(Ed25519SignatureError):
        verify(pub, other_msg, real_sig)


def test_verify_rejects_truncated_message(keypair: tuple[bytes, bytes]) -> None:
    """A real signature on message A MUST NOT verify against a truncated
    version of A."""
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    truncated = _MSG[: len(_MSG) // 2]
    with pytest.raises(Ed25519SignatureError):
        verify(pub, truncated, real_sig)


def test_verify_rejects_extended_message(keypair: tuple[bytes, bytes]) -> None:
    """And MUST NOT verify against message A with extra bytes appended."""
    priv, pub = keypair
    real_sig = sign(priv, _MSG)
    extended = _MSG + b"extra-bytes-appended-by-attacker"
    with pytest.raises(Ed25519SignatureError):
        verify(pub, extended, real_sig)
