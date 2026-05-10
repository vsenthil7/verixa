"""pytest suite for the financial-services policy pack (CP-8.2).

Validates the bundle structure + fixtures parse cleanly. Live OPA
evaluation runs under the integration marker.
"""

from __future__ import annotations

from pathlib import Path

from verixa_runtime.policy.bundle import (
    PolicyTestExpected,
    discover_bundles,
    load_bundle,
    load_fixtures,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
POLICIES_ROOT = REPO_ROOT / "policies"
FS_BUNDLE = POLICIES_ROOT / "financial-services"


# ---------------------------------------------------------------------------
# Bundle structure
# ---------------------------------------------------------------------------


def test_fs_bundle_loads() -> None:
    bundle = load_bundle(FS_BUNDLE)
    assert bundle.name == "financial-services"
    assert bundle.revision == "fs-v1.0.0"
    assert bundle.roots == ("verixa/fs",)


def test_fs_bundle_has_two_policies() -> None:
    bundle = load_bundle(FS_BUNDLE)
    names = {p.name for p in bundle.policies}
    assert {"transfer_amount_limit", "beneficiary_verification"} == names


def test_fs_policy_packages_match_files() -> None:
    bundle = load_bundle(FS_BUNDLE)
    by_name = {p.name: p for p in bundle.policies}
    assert (
        by_name["transfer_amount_limit"].package
        == "verixa.fs.transfer_amount_limit"
    )
    assert (
        by_name["beneficiary_verification"].package
        == "verixa.fs.beneficiary_verification"
    )


def test_fs_bundle_metadata_includes_regulatory_mappings() -> None:
    bundle = load_bundle(FS_BUNDLE)
    mappings = bundle.metadata.get("regulatory_mappings", [])
    assert isinstance(mappings, list)
    frameworks = {m["framework"] for m in mappings if isinstance(m, dict)}
    assert {"FFIEC", "PSD2"}.issubset(frameworks)


# ---------------------------------------------------------------------------
# discover_bundles now finds both core and financial-services
# ---------------------------------------------------------------------------


def test_discover_bundles_finds_core_and_fs() -> None:
    bundles = discover_bundles(POLICIES_ROOT)
    names = [b.name for b in bundles]
    assert "core" in names
    assert "financial-services" in names


def test_discover_bundles_returns_sorted_order() -> None:
    bundles = discover_bundles(POLICIES_ROOT)
    names = [b.name for b in bundles]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# Transfer-amount-limit fixtures
# ---------------------------------------------------------------------------


def test_transfer_limit_fixtures_load() -> None:
    fixtures = load_fixtures(
        FS_BUNDLE / "fixtures" / "transfer_amount_limit_fixtures.json"
    )
    assert len(fixtures) == 5
    pass_count = sum(
        1 for f in fixtures if f.expected_result == PolicyTestExpected.PASS
    )
    fail_count = sum(
        1 for f in fixtures if f.expected_result == PolicyTestExpected.FAIL
    )
    assert pass_count == 2
    assert fail_count == 3


def test_transfer_limit_named_cases_present() -> None:
    fixtures = load_fixtures(
        FS_BUNDLE / "fixtures" / "transfer_amount_limit_fixtures.json"
    )
    names = {f.name for f in fixtures}
    expected = {
        "loan_officer_under_limit_pass",
        "loan_officer_above_limit_fail",
        "junior_clerk_above_low_limit_fail",
        "unknown_role_for_transfer_fail",
        "non_transfer_tool_bypasses_pass",
    }
    assert expected == names


# ---------------------------------------------------------------------------
# Beneficiary-verification fixtures
# ---------------------------------------------------------------------------


def test_beneficiary_fixtures_load() -> None:
    fixtures = load_fixtures(
        FS_BUNDLE / "fixtures" / "beneficiary_verification_fixtures.json"
    )
    assert len(fixtures) == 4
    pass_count = sum(
        1 for f in fixtures if f.expected_result == PolicyTestExpected.PASS
    )
    fail_count = sum(
        1 for f in fixtures if f.expected_result == PolicyTestExpected.FAIL
    )
    assert pass_count == 2
    assert fail_count == 2


def test_beneficiary_named_cases_present() -> None:
    fixtures = load_fixtures(
        FS_BUNDLE / "fixtures" / "beneficiary_verification_fixtures.json"
    )
    names = {f.name for f in fixtures}
    expected = {
        "verified_beneficiary_pass",
        "unverified_beneficiary_fail",
        "missing_beneficiary_field_fail",
        "non_transfer_tool_bypasses_pass",
    }
    assert expected == names


def test_beneficiary_fixtures_carry_psd2_anchor() -> None:
    """Fail-case reasons cite PSD2 Art. 97 (regulatory traceability)."""
    fixtures = load_fixtures(
        FS_BUNDLE / "fixtures" / "beneficiary_verification_fixtures.json"
    )
    fail_reasons = [
        f.expected_reason
        for f in fixtures
        if f.expected_result == PolicyTestExpected.FAIL
    ]
    for reason in fail_reasons:
        assert "PSD2" in reason


# ---------------------------------------------------------------------------
# Source-text spot checks
# ---------------------------------------------------------------------------


def test_transfer_limit_source_includes_role_table() -> None:
    bundle = load_bundle(FS_BUNDLE)
    by_name = {p.name: p for p in bundle.policies}
    src = by_name["transfer_amount_limit"].source_text
    for role in ("junior-clerk", "loan-officer", "senior-officer", "admin"):
        assert role in src


def test_beneficiary_source_references_psd2() -> None:
    bundle = load_bundle(FS_BUNDLE)
    by_name = {p.name: p for p in bundle.policies}
    src = by_name["beneficiary_verification"].source_text
    assert "PSD2" in src
