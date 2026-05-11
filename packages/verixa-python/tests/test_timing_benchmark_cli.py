"""CP-52 tests for tools.timing_benchmark -- the timing-attack investigation harness.

Anchored to Phase-1 carry-forward "timing-attack tripwire investigation".
The harness itself needs tests so the investigation framework is trusted:

  - Robust stats (trimmed_mean / percentiles / IQR) correct on synthetic data
  - cliff_delta correct on known distributions (boundary cases)
  - cliff_delta_magnitude returns correct bands
  - interleaved_samples produces n_samples per condition + invokes both fns
  - evaluate_leak correctly classifies leak vs no-leak on synthetic
    distributions where we control the ground truth
  - experiment_byte0_vs_middle confirms libsodium's Ed25519 verify IS
    constant-time on the cryptographically-relevant comparison
  - experiment_wrong_key_vs_wrong_sig confirms no leak
  - CLI: argument parsing + exit codes + JSON output shape

This file does NOT re-run the full investigation experiments at large N
(they take seconds-to-minutes); the experiments are smoke-tested at N=500
which is enough to verify the plumbing works and produces correct verdicts.
"""

from __future__ import annotations

import json

import pytest

from tools.timing_benchmark import (
    _MSG,
    ComparisonResult,
    TimingStats,
    _flip_bit,
    build_parser,
    cliff_delta,
    cliff_delta_magnitude,
    evaluate_leak,
    experiment_byte0_vs_last,
    experiment_byte0_vs_middle,
    experiment_wrong_key_vs_wrong_sig,
    interleaved_samples,
    main,
)

# ---------------------------------------------------------------------------
# TimingStats
# ---------------------------------------------------------------------------


def test_timing_stats_from_uniform_samples() -> None:
    samples = list(range(1, 101))  # 1..100
    s = TimingStats.from_samples(samples)
    assert s.n == 100
    assert s.min_ns == 1
    assert s.max_ns == 100
    assert s.median_ns == 50.5
    # Trimmed mean drops 10 from each end -> mean of 11..90
    assert s.trimmed_mean_ns == pytest.approx(50.5)
    assert s.p95_ns == 96
    assert s.p99_ns == 100
    # IQR = q3 - q1; q1 = sample at index 25 = 26, q3 at index 75 = 76
    assert s.iqr_ns == pytest.approx(50.0)


def test_timing_stats_rejects_short_samples() -> None:
    with pytest.raises(ValueError, match="at least 10"):
        TimingStats.from_samples([1, 2, 3])


def test_timing_stats_handles_minimum_samples() -> None:
    s = TimingStats.from_samples(list(range(10)))
    assert s.n == 10
    # Trim 10% = 1 from each end -> trimmed_mean of 1..8 = 4.5
    assert s.trimmed_mean_ns == pytest.approx(4.5)


def test_timing_stats_handles_outliers_in_trimmed_mean() -> None:
    """Outliers must NOT dominate trimmed_mean (this is the whole point)."""
    samples = [10] * 90 + [1_000_000] * 10  # 10% massive outliers
    s = TimingStats.from_samples(samples)
    # Raw mean would be ~100_000; trimmed-mean drops the outliers -> ~10
    assert s.trimmed_mean_ns < 100
    assert s.median_ns == 10


# ---------------------------------------------------------------------------
# cliff_delta
# ---------------------------------------------------------------------------


def test_cliff_delta_identical_distributions_is_near_zero() -> None:
    a = list(range(100))
    b = list(range(100))
    d = cliff_delta(a, b)
    # Identical -> roughly zero (small bias from equality handling)
    assert abs(d) < 0.05


def test_cliff_delta_a_strictly_greater_is_plus_one() -> None:
    a = list(range(100, 200))
    b = list(range(0, 100))
    assert cliff_delta(a, b) == pytest.approx(1.0)


def test_cliff_delta_a_strictly_less_is_minus_one() -> None:
    a = list(range(0, 100))
    b = list(range(100, 200))
    assert cliff_delta(a, b) == pytest.approx(-1.0)


def test_cliff_delta_overlapping_distributions() -> None:
    """Half-overlapping distributions produce a moderate-to-large positive delta.

    A is 50..149, B is 0..99 -> a > b on roughly 75% of pairs."""
    a = list(range(50, 150))
    b = list(range(0, 100))
    d = cliff_delta(a, b)
    assert 0.6 < d < 0.85


def test_cliff_delta_rejects_empty_samples() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        cliff_delta([], [1, 2, 3])
    with pytest.raises(ValueError, match="non-empty"):
        cliff_delta([1, 2, 3], [])


# ---------------------------------------------------------------------------
# cliff_delta_magnitude
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "delta,expected",
    [
        (0.0, "negligible"),
        (0.1, "negligible"),
        (0.146, "negligible"),
        (0.147, "small"),
        (0.32, "small"),
        (0.33, "medium"),
        (0.47, "medium"),
        (0.474, "large"),
        (0.5, "large"),
        (1.0, "large"),
        # Negative values: magnitude only cares about abs
        (-0.5, "large"),
        (-0.146, "negligible"),
    ],
)
def test_cliff_delta_magnitude_bands(delta: float, expected: str) -> None:
    assert cliff_delta_magnitude(delta) == expected


# ---------------------------------------------------------------------------
# interleaved_samples
# ---------------------------------------------------------------------------


def test_interleaved_samples_produces_n_per_condition() -> None:
    call_a = [0]
    call_b = [0]

    def fn_a() -> None:
        call_a[0] += 1

    def fn_b() -> None:
        call_b[0] += 1

    a, b = interleaved_samples(fn_a, fn_b, n_samples=50, warmup=5)
    assert len(a) == 50
    assert len(b) == 50
    # Warmup: 5 calls of each. Then 50 samples each. Total: 55 each.
    assert call_a[0] == 55
    assert call_b[0] == 55


def test_interleaved_samples_swallows_verify_exceptions() -> None:
    """_measure_one swallows Ed25519SignatureError + ValueError so we
    can time failing-verify calls. Other exceptions propagate."""
    from verixa_runtime.crypto.ed25519 import Ed25519SignatureError

    def raises_sig_error() -> None:
        raise Ed25519SignatureError("test")

    def raises_value_error() -> None:
        raise ValueError("test")

    a, b = interleaved_samples(
        raises_sig_error, raises_value_error, n_samples=10, warmup=2
    )
    assert len(a) == 10
    assert len(b) == 10
    # All samples should be positive ns counts even though both functions raised
    for sample in a + b:
        assert sample >= 0


def test_interleaved_samples_propagates_unexpected_exceptions() -> None:
    """Non-swallowed exceptions abort the run."""

    def fn_ok() -> None:
        pass

    def fn_oops() -> None:
        raise RuntimeError("unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        interleaved_samples(fn_ok, fn_oops, n_samples=10, warmup=2)


def test_interleaved_samples_rejects_too_few() -> None:
    with pytest.raises(ValueError, match="at least 10"):
        interleaved_samples(lambda: None, lambda: None, n_samples=5)


# ---------------------------------------------------------------------------
# evaluate_leak: classification on synthetic distributions
# ---------------------------------------------------------------------------


def test_evaluate_leak_identical_distributions_reports_no_leak() -> None:
    """When both conditions have identical timing distributions, no leak."""
    a = [100 + i % 5 for i in range(100)]  # 100..104 cycling
    b = [100 + i % 5 for i in range(100)]
    result = evaluate_leak(a, b, name_a="A", name_b="B")
    assert result.leak_detected is False
    assert "No leak" in result.rationale
    assert result.trimmed_mean_ratio == pytest.approx(1.0, abs=0.01)


def test_evaluate_leak_large_difference_reports_leak() -> None:
    """When B is consistently 50% slower than A, leak detected."""
    a = [100 + i % 5 for i in range(100)]
    b = [150 + i % 5 for i in range(100)]
    result = evaluate_leak(a, b, name_a="A", name_b="B")
    assert result.leak_detected is True
    assert "LEAK" in result.rationale
    assert result.trimmed_mean_ratio > 1.3


def test_evaluate_leak_small_difference_below_threshold_no_leak() -> None:
    """Small ratio below 1.05 threshold -> no leak even if statistically detectable."""
    a = [1000 + i % 3 for i in range(200)]  # 1000..1002
    b = [1020 + i % 3 for i in range(200)]  # 1020..1022; ratio ~ 1.02
    result = evaluate_leak(a, b, name_a="A", name_b="B")
    assert result.leak_detected is False
    assert result.trimmed_mean_ratio < 1.05


def test_evaluate_leak_carries_full_stats() -> None:
    a = list(range(100, 200))
    b = list(range(100, 200))
    result = evaluate_leak(a, b, name_a="cond-a", name_b="cond-b")
    assert isinstance(result, ComparisonResult)
    assert result.condition_a_name == "cond-a"
    assert result.condition_b_name == "cond-b"
    assert isinstance(result.condition_a_stats, TimingStats)
    assert isinstance(result.condition_b_stats, TimingStats)


def test_comparison_result_to_json_round_trips() -> None:
    a = list(range(100, 200))
    b = list(range(100, 200))
    result = evaluate_leak(a, b, name_a="A", name_b="B")
    j = result.to_json()
    parsed = json.loads(j)
    assert parsed["condition_a_name"] == "A"
    assert parsed["condition_b_name"] == "B"
    assert "median_ratio" in parsed
    assert "cliff_delta" in parsed
    assert "leak_detected" in parsed


# ---------------------------------------------------------------------------
# Concrete experiments (real Ed25519, but at smoke-test sample size)
# ---------------------------------------------------------------------------


def test_experiment_byte0_vs_middle_no_leak_at_small_n() -> None:
    """The cryptographically-correct comparison: byte0-forged vs byte32-forged.
    Both go through the full crypto path so libsodium's constant-time
    property applies. CP-52 finding: no leak."""
    result = experiment_byte0_vs_middle(n_samples=500)
    # At N=500 the noise floor is wider than at N=10000 but the leak
    # threshold of 1.05 should still come up "no leak" for libsodium.
    # We give a small buffer (1.10 instead of 1.05) so the smoke test
    # is not flaky on CI VMs with worse jitter.
    assert result.trimmed_mean_ratio < 1.10, (
        f"byte0-vs-middle smoke test: trimmed_mean_ratio "
        f"{result.trimmed_mean_ratio:.4f} too high; run full harness "
        f"for definitive investigation."
    )


def test_experiment_wrong_key_vs_wrong_sig_no_leak_at_small_n() -> None:
    """CP-52 finding: no leak; the original CP-36 xfail was small-N noise."""
    result = experiment_wrong_key_vs_wrong_sig(n_samples=500)
    assert result.trimmed_mean_ratio < 1.10, (
        f"wrong-key-vs-wrong-sig smoke test: trimmed_mean_ratio "
        f"{result.trimmed_mean_ratio:.4f} too high; run full harness."
    )


def test_experiment_byte0_vs_last_documents_fast_reject_path() -> None:
    """CP-52 finding: this experiment SHOULD report a leak because bit 511
    triggers libsodium's structural fast-reject. This is NOT a security
    issue (the constraint is public per RFC 8032) but the harness must
    correctly DETECT the timing difference so it would also catch a real
    leak if one existed."""
    result = experiment_byte0_vs_last(n_samples=500)
    # The byte0 vs last-byte comparison should show a large ratio because
    # of the RFC 8032 high-bit constraint fast-reject. This validates
    # the harness sensitivity.
    assert result.trimmed_mean_ratio > 5.0, (
        f"byte0-vs-last expected large ratio (RFC 8032 fast-reject); "
        f"got {result.trimmed_mean_ratio:.4f}"
    )
    assert result.leak_detected is True


# ---------------------------------------------------------------------------
# CLI: parser + main + exit codes
# ---------------------------------------------------------------------------


def test_build_parser_has_required_experiment() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args([])  # missing experiment


def test_build_parser_accepts_all_experiments() -> None:
    p = build_parser()
    for name in ("byte0-vs-last", "byte0-vs-middle", "wrong-key-vs-wrong-sig", "all"):
        ns = p.parse_args([name])
        assert ns.experiment == name


def test_build_parser_default_samples_is_10000() -> None:
    p = build_parser()
    ns = p.parse_args(["byte0-vs-middle"])
    assert ns.samples == 10000


def test_build_parser_json_flag() -> None:
    p = build_parser()
    ns = p.parse_args(["byte0-vs-middle", "--json"])
    assert ns.json is True
    ns2 = p.parse_args(["byte0-vs-middle"])
    assert ns2.json is False


def test_main_rejects_too_few_samples() -> None:
    rc = main(["byte0-vs-middle", "--samples", "5"])
    assert rc == 1


def test_main_byte0_vs_middle_exits_zero_at_small_n(capsys) -> None:
    """The clean-comparison experiment exits 0 (no leak)."""
    rc = main(["byte0-vs-middle", "--samples", "500"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "no leak" in captured.out.lower()


def test_main_byte0_vs_last_exits_two_at_small_n(capsys) -> None:
    """The structural-fast-reject experiment exits 2 (LEAK reported)."""
    rc = main(["byte0-vs-last", "--samples", "500"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "leak" in captured.out.lower()


def test_main_json_output_is_parseable(capsys) -> None:
    rc = main(["byte0-vs-middle", "--samples", "500", "--json"])
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "byte0-vs-middle" in parsed
    assert "any_leak_detected" in parsed
    assert rc in (0, 2)


def test_main_all_runs_every_experiment(capsys) -> None:
    """The 'all' experiment runs every experiment; exit code reflects the
    UNION of leak verdicts (so byte0-vs-last reporting LEAK forces exit 2
    even though byte0-vs-middle reports no leak)."""
    rc = main(["all", "--samples", "500"])
    assert rc == 2  # byte0-vs-last reports LEAK
    captured = capsys.readouterr()
    assert "byte0-vs-last" in captured.out
    assert "byte0-vs-middle" in captured.out
    assert "wrong-key-vs-wrong-sig" in captured.out


def test_flip_bit_round_trips() -> None:
    """Flipping the same bit twice returns the original buffer."""
    buf = b"\x00\x00\x00"
    flipped = _flip_bit(buf, 5)
    twice = _flip_bit(flipped, 5)
    assert twice == buf
    # And the single flip should differ
    assert flipped != buf


def test_msg_is_canonical_bytes() -> None:
    """The canonical test message is stable so test re-runs are
    comparable to historical harness output."""
    assert _MSG == b"verixa-timing-attack-canonical-test-message"
    assert isinstance(_MSG, bytes)
