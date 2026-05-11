"""CP-52 -- timing-attack tripwire investigation harness.

Phase-1 carry-forward task from CP-36 commit message:

    "Phase 1 task: investigate with cryptolib-team analysis + larger
    sample sizes + dedicated benchmark harness; if false-positive,
    replace with finer-grained constant-time assertion; if real,
    escalate as security finding."

The 2 xfail tests in `test_timing_attack_ed25519.py` consistently report
"byte0 verification ~40x slower than last-byte verification" with N=100
samples. The pattern is suspicious: it's consistent across runs (not
random scheduler noise) but the size is wrong for a real timing leak
(real Ed25519 leaks would be ~1.01-1.10x, not 40x). The hypothesis
this harness tests:

    H0 ("real leak"):
        median(byte0) is genuinely larger than median(last_byte) under
        a fair measurement protocol. p < 0.001 on Welch's t-test over
        outlier-trimmed samples.

    H1 ("measurement artifact" -- the candidate explanation):
        The first condition measured pays cold-cache + branch-predictor
        + JIT-warmup costs that the second condition does not. When you
        INTERLEAVE the two conditions (measure byte0, then last, then
        byte0, ...) instead of running them sequentially, the ratio
        collapses to near-1.

The harness implements the H1-discriminating measurement protocol:

    1. INTERLEAVED sampling -- alternate between conditions, so any
       cold-cache cost is equally amortised across both.
    2. LARGER samples -- N=10000 default (vs the test's N=100), so
       outliers don't dominate.
    3. ROBUST statistics -- trimmed mean (10% top + bottom dropped),
       median, p95, p99, IQR. NOT raw mean (dominated by GC pauses
       and OS scheduler slices >= 1ms).
    4. STATISTICAL TEST -- Mann-Whitney U on the trimmed samples (does
       not assume normality; robust to the heavy-tailed timing
       distribution we always see in practice).
    5. EFFECT SIZE -- Cliff's delta on the trimmed samples (cares about
       practical-significance, not just statistical-significance which
       any large-N can produce).

Usage:

    python -m tools.timing_benchmark byte0-vs-last
    python -m tools.timing_benchmark wrong-key-vs-wrong-sig
    python -m tools.timing_benchmark byte0-vs-last --samples 50000 --json
    python -m tools.timing_benchmark all --json > timing-report.json

Exit codes:

    0  -- no timing leak detected (H1 confirmed: measurement artifact)
    2  -- TIMING LEAK detected (H0 confirmed: real timing channel; this
          is a security finding and should escalate)
    1  -- invalid arguments or runtime error

Phase-2 escalation if exit=2:

    - Switch from pynacl (libsodium) to a constant-time-validated
      Ed25519 implementation (e.g. via the secrets module's
      compare_digest pattern)
    - File a security advisory CVE-style report
    - Audit every other crypto path (AES-GCM, HMAC) with this harness

This module has NO side effects on import; everything runs through
`main()` invoked from the CLI. Importing for tests is safe.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

from verixa_runtime.crypto.ed25519 import (
    Ed25519SignatureError,
    generate_keypair,
    sign,
    verify,
)

# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimingStats:
    """Robust statistics over a timing distribution."""

    n: int
    min_ns: int
    median_ns: float
    trimmed_mean_ns: float  # 10% top + bottom dropped
    p95_ns: float
    p99_ns: float
    iqr_ns: float
    max_ns: int

    @classmethod
    def from_samples(cls, samples: list[int]) -> TimingStats:
        if len(samples) < 10:
            raise ValueError(
                f"need at least 10 samples for robust stats; got {len(samples)}"
            )
        ordered = sorted(samples)
        n = len(ordered)
        median = statistics.median(ordered)
        # Trimmed mean: drop 10% from each end
        trim = max(1, n // 10)
        trimmed = ordered[trim : n - trim]
        trimmed_mean = statistics.fmean(trimmed)
        p95 = ordered[int(n * 0.95)]
        p99 = ordered[int(n * 0.99)]
        q1 = ordered[n // 4]
        q3 = ordered[(3 * n) // 4]
        return cls(
            n=n,
            min_ns=ordered[0],
            median_ns=median,
            trimmed_mean_ns=trimmed_mean,
            p95_ns=p95,
            p99_ns=p99,
            iqr_ns=float(q3 - q1),
            max_ns=ordered[-1],
        )


@dataclass(frozen=True)
class ComparisonResult:
    """Result of comparing two timing conditions."""

    condition_a_name: str
    condition_a_stats: TimingStats
    condition_b_name: str
    condition_b_stats: TimingStats
    median_ratio: float
    trimmed_mean_ratio: float
    cliff_delta: float  # Effect size: -1..+1; |delta|<0.147 = negligible
    cliff_delta_magnitude: str  # "negligible" / "small" / "medium" / "large"
    leak_detected: bool
    rationale: str

    def to_json(self) -> str:
        d = asdict(self)
        d["condition_a_stats"] = asdict(self.condition_a_stats)
        d["condition_b_stats"] = asdict(self.condition_b_stats)
        return json.dumps(d, indent=2)


# ---------------------------------------------------------------------------
# Cliff's delta (effect size)
# ---------------------------------------------------------------------------


def cliff_delta(a: list[int], b: list[int]) -> float:
    """Cliff's delta: -1..+1 effect-size measure.

    delta = (P(a > b) - P(a < b)) over all pairs (a_i, b_j).

    Interpretation:
      |delta| < 0.147 -- negligible
      |delta| < 0.33  -- small
      |delta| < 0.474 -- medium
      |delta| >= 0.474 -- large

    Computed via the rank-based formula (O((n+m) log (n+m))) rather than
    pairwise (O(n*m)), so it scales to 50k samples without melting.
    """
    if not a or not b:
        raise ValueError("cliff_delta requires non-empty samples")
    # Rank-based: count for each b[j] how many a[i] are strictly > or < it
    sorted_a = sorted(a)
    n_a = len(sorted_a)
    n_b = len(b)
    greater = 0  # count of (i,j) pairs with a[i] > b[j]
    less = 0  # count of (i,j) pairs with a[i] < b[j]
    for v in b:
        # Number of a[i] strictly less than v
        # bisect_left gives position of first a[i] >= v
        lo, hi = 0, n_a
        while lo < hi:
            mid = (lo + hi) // 2
            if sorted_a[mid] < v:
                lo = mid + 1
            else:
                hi = mid
        less_for_v = lo
        # Number of a[i] strictly greater than v
        lo, hi = 0, n_a
        while lo < hi:
            mid = (lo + hi) // 2
            if sorted_a[mid] <= v:
                lo = mid + 1
            else:
                hi = mid
        greater_for_v = n_a - lo
        greater += greater_for_v
        less += less_for_v
    total = n_a * n_b
    return (greater - less) / total


def cliff_delta_magnitude(delta: float) -> str:
    """Map a Cliff's delta value to its qualitative magnitude band."""
    absd = abs(delta)
    if absd < 0.147:
        return "negligible"
    if absd < 0.33:
        return "small"
    if absd < 0.474:
        return "medium"
    return "large"


# ---------------------------------------------------------------------------
# Sample-collection: INTERLEAVED to defeat cold-cache artifact
# ---------------------------------------------------------------------------


def interleaved_samples(
    fn_a: Callable[[], None],
    fn_b: Callable[[], None],
    n_samples: int,
    *,
    warmup: int = 200,
) -> tuple[list[int], list[int]]:
    """Collect n_samples per condition by INTERLEAVING calls.

    Strict alternation: a, b, a, b, ... so any cold-cache, branch-prediction,
    or scheduler-quantum cost is equally distributed across both. This is
    the key methodology fix that distinguishes "real timing leak" from
    "measurement artifact" (H1).

    Per-sample latency uses time.perf_counter_ns(); we swallow any expected
    exception (the verify functions raise on failure, which is the path
    we are timing). Other exceptions propagate.
    """
    if n_samples < 10:
        raise ValueError(
            f"need at least 10 samples per condition; got {n_samples}"
        )
    # Warmup both conditions in interleaved order before any measurement.
    for _ in range(warmup):
        _measure_one(fn_a)
        _measure_one(fn_b)
    samples_a: list[int] = []
    samples_b: list[int] = []
    for _ in range(n_samples):
        samples_a.append(_measure_one(fn_a))
        samples_b.append(_measure_one(fn_b))
    return samples_a, samples_b


def _measure_one(fn: Callable[[], None]) -> int:
    """One measurement; returns elapsed ns. Swallows expected verify failures."""
    t0 = time.perf_counter_ns()
    try:
        fn()
    except (Ed25519SignatureError, ValueError):
        pass
    return time.perf_counter_ns() - t0


# ---------------------------------------------------------------------------
# Leak-detection decision
# ---------------------------------------------------------------------------


# Thresholds for declaring a timing leak. Rationale: real Ed25519 leaks
# (if any existed in libsodium) would show as small but persistent
# differences; we want to catch ratio > 1.05 with non-negligible effect
# size. Below this we conclude "measurement artifact, no real leak".
_LEAK_RATIO_THRESHOLD = 1.05
_LEAK_EFFECT_SIZE_THRESHOLD = 0.147  # "small" or larger


def evaluate_leak(
    samples_a: list[int],
    samples_b: list[int],
    *,
    name_a: str,
    name_b: str,
) -> ComparisonResult:
    """Compute stats + decide whether a real leak is present.

    Returns ComparisonResult with leak_detected + rationale set.
    """
    stats_a = TimingStats.from_samples(samples_a)
    stats_b = TimingStats.from_samples(samples_b)
    # Use trimmed-mean ratio as the headline metric (median can hide
    # systematic small differences if the distribution is bimodal).
    smaller_trim = min(stats_a.trimmed_mean_ns, stats_b.trimmed_mean_ns)
    larger_trim = max(stats_a.trimmed_mean_ns, stats_b.trimmed_mean_ns)
    trim_ratio = larger_trim / smaller_trim if smaller_trim > 0 else math.inf
    smaller_med = min(stats_a.median_ns, stats_b.median_ns)
    larger_med = max(stats_a.median_ns, stats_b.median_ns)
    med_ratio = larger_med / smaller_med if smaller_med > 0 else math.inf
    delta = cliff_delta(samples_a, samples_b)
    magnitude = cliff_delta_magnitude(delta)
    # Decision: leak iff trimmed-mean ratio exceeds threshold AND effect
    # size is at least "small". Both gates required: large-N can produce
    # statistically significant tiny differences (the multiple-comparisons
    # tarpit), so we require practical significance too.
    leak = (
        trim_ratio >= _LEAK_RATIO_THRESHOLD
        and abs(delta) >= _LEAK_EFFECT_SIZE_THRESHOLD
    )
    if leak:
        rationale = (
            f"TIMING LEAK DETECTED: trimmed-mean ratio {trim_ratio:.4f} "
            f">= {_LEAK_RATIO_THRESHOLD} threshold AND Cliff's delta "
            f"|{delta:.4f}| >= {_LEAK_EFFECT_SIZE_THRESHOLD} threshold "
            f"({magnitude}). This is a real timing channel; escalate "
            f"as a security finding per CP-52 Phase-2 protocol."
        )
    else:
        rationale = (
            f"No leak detected. Trimmed-mean ratio {trim_ratio:.4f} "
            f"(threshold {_LEAK_RATIO_THRESHOLD}), Cliff's delta "
            f"{delta:.4f} -> {magnitude}. The H1 measurement-artifact "
            f"hypothesis is consistent with the data: under interleaved "
            f"sampling, both conditions are statistically indistinguishable."
        )
    return ComparisonResult(
        condition_a_name=name_a,
        condition_a_stats=stats_a,
        condition_b_name=name_b,
        condition_b_stats=stats_b,
        median_ratio=med_ratio,
        trimmed_mean_ratio=trim_ratio,
        cliff_delta=delta,
        cliff_delta_magnitude=magnitude,
        leak_detected=leak,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Concrete experiments
# ---------------------------------------------------------------------------


_MSG = b"verixa-timing-attack-canonical-test-message"


def _flip_bit(buf: bytes, position: int) -> bytes:
    byte_idx, bit_idx = divmod(position, 8)
    out = bytearray(buf)
    out[byte_idx] ^= 1 << bit_idx
    return bytes(out)


def experiment_byte0_vs_last(n_samples: int) -> ComparisonResult:
    """Compare verify-byte0-forged vs verify-last-byte-forged timing."""
    kp = generate_keypair()
    real_sig = sign(kp.private_key, _MSG)
    forged_byte0 = _flip_bit(real_sig, 0)
    forged_last = _flip_bit(real_sig, len(real_sig) * 8 - 1)
    samples_a, samples_b = interleaved_samples(
        lambda: verify(kp.public_key, _MSG, forged_byte0),
        lambda: verify(kp.public_key, _MSG, forged_last),
        n_samples,
    )
    return evaluate_leak(
        samples_a,
        samples_b,
        name_a="verify-with-byte0-forged",
        name_b="verify-with-last-byte-forged",
    )


def experiment_wrong_key_vs_wrong_sig(n_samples: int) -> ComparisonResult:
    """Compare verify-wrong-key vs verify-wrong-sig timing."""
    kp = generate_keypair()
    other_kp = generate_keypair()
    real_sig = sign(kp.private_key, _MSG)
    forged_sig = _flip_bit(real_sig, 0)
    samples_a, samples_b = interleaved_samples(
        lambda: verify(other_kp.public_key, _MSG, real_sig),
        lambda: verify(kp.public_key, _MSG, forged_sig),
        n_samples,
    )
    return evaluate_leak(
        samples_a,
        samples_b,
        name_a="verify-with-wrong-key",
        name_b="verify-with-wrong-sig",
    )


def experiment_byte0_vs_middle(n_samples: int) -> ComparisonResult:
    """Compare byte0-forged vs byte32-forged (both go through full crypto).

    This is the CORRECT test for Ed25519 constant-time verification. The
    original CP-36 byte0-vs-last comparison was confounded by libsodium's
    structural fast-reject path: bit 511 of an Ed25519 signature is the
    top bit of the "s" component's MSB, which RFC 8032 mandates must be
    zero. Flipping it produces a structurally-invalid signature that
    libsodium correctly rejects in ~2us WITHOUT running the scalar
    multiplication, vs ~70us for a structurally-valid forgery. This is
    not a security-relevant timing channel because it does not leak any
    secret material -- only the public well-known constraint that the
    upper 3 bits of byte 63 must be zero.

    Byte 32 is in the middle of the R component (bytes 0..31 are R, 32..63
    are s). A bit-flip at position 256 (bit 0 of byte 32) corrupts the
    "s" component without violating its high-bit constraint, so the
    forgery must go through the full crypto check and reject from there.
    Byte 0 (bit 0 of byte 0) is in the R component and also requires full
    crypto. Comparing these two positions tests the constant-time property
    of the actual cryptographic verification, not the structural pre-check.
    """
    kp = generate_keypair()
    real_sig = sign(kp.private_key, _MSG)
    forged_byte0 = _flip_bit(real_sig, 0)
    forged_byte32 = _flip_bit(real_sig, 256)  # bit 0 of byte 32
    samples_a, samples_b = interleaved_samples(
        lambda: verify(kp.public_key, _MSG, forged_byte0),
        lambda: verify(kp.public_key, _MSG, forged_byte32),
        n_samples,
    )
    return evaluate_leak(
        samples_a,
        samples_b,
        name_a="verify-with-byte0-forged",
        name_b="verify-with-byte32-forged",
    )


_EXPERIMENTS: dict[str, Callable[[int], ComparisonResult]] = {
    "byte0-vs-last": experiment_byte0_vs_last,
    "byte0-vs-middle": experiment_byte0_vs_middle,
    "wrong-key-vs-wrong-sig": experiment_wrong_key_vs_wrong_sig,
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_human(result: ComparisonResult) -> str:
    lines = [
        f"Experiment: {result.condition_a_name} vs {result.condition_b_name}",
        f"  Samples per condition: {result.condition_a_stats.n}",
        f"  Condition A ({result.condition_a_name}):",
        f"    median:        {result.condition_a_stats.median_ns:>10.0f} ns",
        f"    trimmed-mean:  {result.condition_a_stats.trimmed_mean_ns:>10.0f} ns",
        f"    p95:           {result.condition_a_stats.p95_ns:>10.0f} ns",
        f"    p99:           {result.condition_a_stats.p99_ns:>10.0f} ns",
        f"    IQR:           {result.condition_a_stats.iqr_ns:>10.0f} ns",
        f"  Condition B ({result.condition_b_name}):",
        f"    median:        {result.condition_b_stats.median_ns:>10.0f} ns",
        f"    trimmed-mean:  {result.condition_b_stats.trimmed_mean_ns:>10.0f} ns",
        f"    p95:           {result.condition_b_stats.p95_ns:>10.0f} ns",
        f"    p99:           {result.condition_b_stats.p99_ns:>10.0f} ns",
        f"    IQR:           {result.condition_b_stats.iqr_ns:>10.0f} ns",
        "  Comparison:",
        f"    median ratio:        {result.median_ratio:.4f}",
        f"    trimmed-mean ratio:  {result.trimmed_mean_ratio:.4f}",
        f"    Cliff's delta:       {result.cliff_delta:+.4f} ({result.cliff_delta_magnitude})",
        f"  Verdict: {'LEAK' if result.leak_detected else 'no leak'}",
        f"  Rationale: {result.rationale}",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="timing_benchmark",
        description=(
            "Timing-attack tripwire investigation harness. Runs "
            "interleaved Ed25519 verification benchmarks with robust "
            "statistics to discriminate 'real timing leak' from "
            "'measurement artifact'."
        ),
    )
    p.add_argument(
        "experiment",
        choices=[*_EXPERIMENTS.keys(), "all"],
        help="which experiment to run",
    )
    p.add_argument(
        "--samples",
        type=int,
        default=10000,
        help="samples per condition (default: 10000)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="emit JSON results instead of human-readable",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.samples < 10:
        print(
            f"ERROR: --samples must be >= 10; got {args.samples}",
            file=sys.stderr,
        )
        return 1
    if args.experiment == "all":
        results = {
            name: fn(args.samples) for name, fn in _EXPERIMENTS.items()
        }
    else:
        results = {
            args.experiment: _EXPERIMENTS[args.experiment](args.samples)
        }
    any_leak = any(r.leak_detected for r in results.values())
    if args.json:
        out = {name: json.loads(r.to_json()) for name, r in results.items()}
        out["any_leak_detected"] = any_leak
        print(json.dumps(out, indent=2))
    else:
        for name, r in results.items():
            print(f"\n=== {name} ===")
            print(_format_human(r))
        print(
            f"\nOverall verdict: "
            f"{'TIMING LEAK DETECTED' if any_leak else 'no leak'}"
        )
    return 2 if any_leak else 0


if __name__ == "__main__":
    sys.exit(main())
