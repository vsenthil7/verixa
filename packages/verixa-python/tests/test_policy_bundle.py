"""pytest suite for verixa_runtime.policy.bundle (CP-8.1).

Two layers:
  1. Real-bundle tests: walk the on-disk ``policies/core/`` and confirm
     the structure parses cleanly + matches expected packages and
     policy names.
  2. Synthetic-bundle tests: tmp_path scenarios for every error path
     (malformed manifest, missing rego, bad package declaration,
     unknown expected_result) so the loader hits 100% branch coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from verixa_runtime.policy.bundle import (
    PolicyBundleError,
    PolicyEntry,
    PolicyFixture,
    PolicyTestExpected,
    discover_bundles,
    load_bundle,
    load_fixtures,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
POLICIES_ROOT = REPO_ROOT / "policies"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_expected_enum_values() -> None:
    assert {x.value for x in PolicyTestExpected} == {"pass", "fail", "abstain"}


# ---------------------------------------------------------------------------
# Real bundle: policies/core/
# ---------------------------------------------------------------------------


def test_core_bundle_loads() -> None:
    bundle = load_bundle(POLICIES_ROOT / "core")
    assert bundle.name == "core"
    assert bundle.revision == "core-v1.0.0"
    assert bundle.roots == ("verixa/core",)
    assert isinstance(bundle.metadata, dict)
    assert bundle.metadata.get("compliance_pack") == "core"


def test_core_bundle_has_two_policies() -> None:
    bundle = load_bundle(POLICIES_ROOT / "core")
    names = {p.name for p in bundle.policies}
    assert {"pii_redaction", "workflow_role_binding"}.issubset(names)


def test_core_policy_packages_match_files() -> None:
    bundle = load_bundle(POLICIES_ROOT / "core")
    by_name = {p.name: p for p in bundle.policies}
    assert by_name["pii_redaction"].package == "verixa.core.pii_redaction"
    assert (
        by_name["workflow_role_binding"].package
        == "verixa.core.workflow_role_binding"
    )


def test_discover_bundles_finds_core() -> None:
    bundles = discover_bundles(POLICIES_ROOT)
    names = [b.name for b in bundles]
    assert "core" in names


# ---------------------------------------------------------------------------
# Real fixtures: policies/core/fixtures/
# ---------------------------------------------------------------------------


def test_pii_fixtures_load() -> None:
    path = POLICIES_ROOT / "core" / "fixtures" / "pii_redaction_fixtures.json"
    fixtures = load_fixtures(path)
    assert len(fixtures) == 3
    names = {f.name for f in fixtures}
    assert "clean_arguments_pass" in names
    assert "ssn_in_argument_fail" in names
    assert "pan_in_memo_fail" in names


def test_workflow_role_fixtures_load() -> None:
    path = (
        POLICIES_ROOT
        / "core"
        / "fixtures"
        / "workflow_role_binding_fixtures.json"
    )
    fixtures = load_fixtures(path)
    assert len(fixtures) == 4
    pass_count = sum(
        1 for f in fixtures if f.expected_result == PolicyTestExpected.PASS
    )
    fail_count = sum(
        1 for f in fixtures if f.expected_result == PolicyTestExpected.FAIL
    )
    assert pass_count == 2
    assert fail_count == 2


def test_fixture_input_contains_governrequest_shape() -> None:
    fixtures = load_fixtures(
        POLICIES_ROOT / "core" / "fixtures" / "pii_redaction_fixtures.json"
    )
    f = fixtures[0]
    assert "agent_identity" in f.input
    assert "action" in f.input
    assert "context" in f.input


# ---------------------------------------------------------------------------
# Synthetic bundle error paths
# ---------------------------------------------------------------------------


def _write_minimal_bundle(
    bundle_dir: Path,
    *,
    manifest_text: str | None = None,
    rego_files: dict[str, str] | None = None,
) -> Path:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    if manifest_text is not None:
        (bundle_dir / ".manifest").write_text(manifest_text, encoding="utf-8")
    if rego_files:
        for name, text in rego_files.items():
            (bundle_dir / name).write_text(text, encoding="utf-8")
    return bundle_dir


def test_load_bundle_rejects_non_directory(tmp_path: Path) -> None:
    f = tmp_path / "not_a_dir.txt"
    f.write_text("hi", encoding="utf-8")
    with pytest.raises(PolicyBundleError, match="not a directory"):
        load_bundle(f)


def test_load_bundle_missing_manifest(tmp_path: Path) -> None:
    bundle = tmp_path / "bad_pack"
    bundle.mkdir()
    with pytest.raises(PolicyBundleError, match="missing .manifest"):
        load_bundle(bundle)


def test_load_bundle_invalid_json_manifest(tmp_path: Path) -> None:
    _write_minimal_bundle(
        tmp_path / "bad_json", manifest_text="this is not json"
    )
    with pytest.raises(PolicyBundleError, match="invalid JSON"):
        load_bundle(tmp_path / "bad_json")


def test_load_bundle_manifest_not_object(tmp_path: Path) -> None:
    _write_minimal_bundle(
        tmp_path / "list_manifest", manifest_text=json.dumps([1, 2, 3])
    )
    with pytest.raises(PolicyBundleError, match="must be a JSON object"):
        load_bundle(tmp_path / "list_manifest")


def test_load_bundle_manifest_missing_revision(tmp_path: Path) -> None:
    _write_minimal_bundle(
        tmp_path / "no_rev",
        manifest_text=json.dumps({"roots": []}),
    )
    with pytest.raises(PolicyBundleError, match="missing required key 'revision'"):
        load_bundle(tmp_path / "no_rev")


def test_load_bundle_manifest_missing_roots(tmp_path: Path) -> None:
    _write_minimal_bundle(
        tmp_path / "no_roots",
        manifest_text=json.dumps({"revision": "v1"}),
    )
    with pytest.raises(PolicyBundleError, match="missing required key 'roots'"):
        load_bundle(tmp_path / "no_roots")


def test_load_bundle_manifest_roots_not_list(tmp_path: Path) -> None:
    _write_minimal_bundle(
        tmp_path / "bad_roots",
        manifest_text=json.dumps({"revision": "v1", "roots": "not-a-list"}),
    )
    with pytest.raises(PolicyBundleError, match="'roots' must be a list"):
        load_bundle(tmp_path / "bad_roots")


def test_load_bundle_no_rego_files(tmp_path: Path) -> None:
    _write_minimal_bundle(
        tmp_path / "empty_pack",
        manifest_text=json.dumps({"revision": "v1", "roots": ["x"]}),
    )
    with pytest.raises(PolicyBundleError, match="no .rego policies"):
        load_bundle(tmp_path / "empty_pack")


def test_load_bundle_rego_no_package(tmp_path: Path) -> None:
    _write_minimal_bundle(
        tmp_path / "no_package",
        manifest_text=json.dumps({"revision": "v1", "roots": ["x"]}),
        rego_files={"a.rego": "# only comments\n# nothing else\n"},
    )
    with pytest.raises(PolicyBundleError, match="no package declaration"):
        load_bundle(tmp_path / "no_package")


def test_load_bundle_rego_first_line_not_package(tmp_path: Path) -> None:
    _write_minimal_bundle(
        tmp_path / "wrong_first_line",
        manifest_text=json.dumps({"revision": "v1", "roots": ["x"]}),
        rego_files={
            "a.rego": "import rego.v1\npackage verixa.x\n",
        },
    )
    with pytest.raises(PolicyBundleError, match="not a package declaration"):
        load_bundle(tmp_path / "wrong_first_line")


def test_load_bundle_rego_empty_package_name(tmp_path: Path) -> None:
    _write_minimal_bundle(
        tmp_path / "empty_pkg",
        manifest_text=json.dumps({"revision": "v1", "roots": ["x"]}),
        rego_files={"a.rego": "package \n"},
    )
    with pytest.raises(PolicyBundleError, match="empty package declaration"):
        load_bundle(tmp_path / "empty_pkg")


def test_load_bundle_skips_blank_and_comment_lines_before_package(
    tmp_path: Path,
) -> None:
    """Blank lines and # comments before package are tolerated."""
    _write_minimal_bundle(
        tmp_path / "ok_pkg",
        manifest_text=json.dumps({"revision": "v1", "roots": ["x"]}),
        rego_files={
            "a.rego": (
                "# header comment\n"
                "\n"
                "# more comment\n"
                "package verixa.x\n"
            )
        },
    )
    bundle = load_bundle(tmp_path / "ok_pkg")
    assert bundle.policies[0].package == "verixa.x"


# ---------------------------------------------------------------------------
# discover_bundles
# ---------------------------------------------------------------------------


def test_discover_bundles_rejects_non_directory(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi")
    with pytest.raises(PolicyBundleError, match="not a directory"):
        discover_bundles(f)


def test_discover_bundles_skips_dirs_without_manifest(tmp_path: Path) -> None:
    """Directories under policies_root without .manifest are skipped."""
    (tmp_path / "doc_only").mkdir()
    (tmp_path / "doc_only" / "README.md").write_text("# nope")
    _write_minimal_bundle(
        tmp_path / "real_pack",
        manifest_text=json.dumps({"revision": "v1", "roots": ["x"]}),
        rego_files={"p.rego": "package verixa.x\n"},
    )
    bundles = discover_bundles(tmp_path)
    assert [b.name for b in bundles] == ["real_pack"]


def test_discover_bundles_skips_files_at_root(tmp_path: Path) -> None:
    """A regular file (not a dir) at policies_root is silently skipped."""
    (tmp_path / "stray.txt").write_text("ignore me")
    _write_minimal_bundle(
        tmp_path / "real",
        manifest_text=json.dumps({"revision": "v1", "roots": ["x"]}),
        rego_files={"p.rego": "package verixa.x\n"},
    )
    bundles = discover_bundles(tmp_path)
    assert [b.name for b in bundles] == ["real"]


# ---------------------------------------------------------------------------
# load_fixtures error paths
# ---------------------------------------------------------------------------


def test_load_fixtures_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PolicyBundleError, match="fixtures file not found"):
        load_fixtures(tmp_path / "nope.json")


def test_load_fixtures_root_not_object(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(PolicyBundleError, match="root must be a JSON object"):
        load_fixtures(p)


def test_load_fixtures_fixtures_not_list(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"fixtures": "string"}), encoding="utf-8")
    with pytest.raises(PolicyBundleError, match="must be a list"):
        load_fixtures(p)


def test_load_fixtures_item_not_object(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"fixtures": ["string"]}), encoding="utf-8")
    with pytest.raises(PolicyBundleError, match="not an object"):
        load_fixtures(p)


def test_load_fixtures_item_missing_required_field(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(
        json.dumps({"fixtures": [{"name": "x", "input": {}}]}),
        encoding="utf-8",
    )
    with pytest.raises(PolicyBundleError, match="missing 'expected_result'"):
        load_fixtures(p)


def test_load_fixtures_invalid_expected_result(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(
        json.dumps(
            {
                "fixtures": [
                    {
                        "name": "x",
                        "expected_result": "maybe",
                        "input": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PolicyBundleError, match="invalid expected_result"):
        load_fixtures(p)


def test_load_fixtures_default_empty_reason(tmp_path: Path) -> None:
    """expected_reason defaults to empty string when omitted."""
    p = tmp_path / "x.json"
    p.write_text(
        json.dumps(
            {
                "fixtures": [
                    {"name": "n", "expected_result": "pass", "input": {}}
                ]
            }
        ),
        encoding="utf-8",
    )
    fixtures = load_fixtures(p)
    assert fixtures[0].expected_reason == ""


# ---------------------------------------------------------------------------
# Frozen invariants + reexports
# ---------------------------------------------------------------------------


def test_policy_entry_is_frozen() -> None:
    e = PolicyEntry(
        name="x",
        package="verixa.x",
        source_path=Path("/x.rego"),
        source_text="",
    )
    with pytest.raises((AttributeError, Exception)):
        e.name = "y"  # type: ignore[misc]


def test_policy_fixture_is_frozen() -> None:
    f = PolicyFixture(
        name="x",
        expected_result=PolicyTestExpected.PASS,
        expected_reason="",
        input={},
    )
    with pytest.raises((AttributeError, Exception)):
        f.name = "y"  # type: ignore[misc]


def test_policy_package_reexports() -> None:
    from verixa_runtime import policy

    for name in (
        "PolicyBundle",
        "PolicyBundleError",
        "PolicyEntry",
        "PolicyFixture",
        "PolicyTestExpected",
        "discover_bundles",
        "load_bundle",
        "load_fixtures",
    ):
        assert hasattr(policy, name), f"policy package missing {name}"
