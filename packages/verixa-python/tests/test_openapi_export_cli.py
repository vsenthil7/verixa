"""CP-54 tests for tools.openapi_export -- schema export + drift-detection CLI.

Anchored to Phase-1 carry-forward "checked-in OpenAPI schema for SDK
generation + drift detection". Tests cover:

  - _normalise: deterministic JSON serialisation (sort-keys + indent)
  - _read_committed: round-trip + missing-file rejection
  - _cmd_generate writes a parseable JSON file with all expected fields
  - _cmd_diff returns 0 on match, 2 on drift, 1 on missing-artifact
  - _cmd_diff detects route additions + removals + body-only changes
  - _cmd_show prints metadata + verbose path listing
  - CLI argparse + exit codes + custom paths

This file also pins the high-level shape of the COMMITTED docs/openapi.json
artifact (path count + key path presence + openapi version) so any
unintended schema change to the control plane fails the test suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.openapi_export import (
    _DEFAULT_ARTIFACT,
    _cmd_diff,
    _cmd_generate,
    _cmd_show,
    _generate_live_schema,
    _normalise,
    _read_committed,
    build_parser,
    main,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# _normalise
# ---------------------------------------------------------------------------


def test_normalise_sorts_keys() -> None:
    spec = {"b": 1, "a": 2}
    out = _normalise(spec)
    # 'a' must appear before 'b'
    assert out.index('"a"') < out.index('"b"')


def test_normalise_uses_2_space_indent() -> None:
    spec = {"outer": {"inner": 1}}
    out = _normalise(spec)
    assert '\n  "outer"' in out  # 2-space indent at depth 1
    assert '\n    "inner"' in out  # 4-space indent at depth 2


def test_normalise_ends_with_newline() -> None:
    out = _normalise({"a": 1})
    assert out.endswith("\n")


def test_normalise_is_deterministic() -> None:
    spec = {"z": 1, "a": 2, "m": {"q": 3, "b": 4}}
    out1 = _normalise(spec)
    out2 = _normalise(spec)
    assert out1 == out2


# ---------------------------------------------------------------------------
# _read_committed
# ---------------------------------------------------------------------------


def test_read_committed_returns_canonical_string(tmp_path: Path) -> None:
    target = tmp_path / "spec.json"
    target.write_text('{"a": 1}\n', encoding="utf-8")
    content = _read_committed(target)
    assert content == '{"a": 1}\n'


def test_read_committed_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="committed schema not found"):
        _read_committed(tmp_path / "missing.json")


# ---------------------------------------------------------------------------
# _generate_live_schema
# ---------------------------------------------------------------------------


def test_generate_live_schema_returns_openapi_dict() -> None:
    spec = _generate_live_schema()
    assert isinstance(spec, dict)
    assert spec["openapi"].startswith("3.")
    assert "paths" in spec
    assert "info" in spec


def test_generate_live_schema_includes_v1_control_routes() -> None:
    spec = _generate_live_schema()
    paths = spec["paths"]
    # Sanity: core control-plane routes are registered
    assert "/v1/control/workflows" in paths
    assert "/v1/control/agents" in paths
    assert "/v1/control/audit" in paths
    assert "/v1/control/replay" in paths
    assert "/v1/control/dossier" in paths
    assert "/v1/control/dossier/{dossier_id}" in paths


def test_generate_live_schema_includes_operational_endpoints() -> None:
    spec = _generate_live_schema()
    paths = spec["paths"]
    assert "/healthz" in paths
    assert "/readyz" in paths
    assert "/metrics" in paths


# ---------------------------------------------------------------------------
# _cmd_generate writes a parseable file
# ---------------------------------------------------------------------------


def test_cmd_generate_writes_parseable_json(tmp_path: Path) -> None:
    out_path = tmp_path / "spec.json"

    class Args:
        out = str(out_path)

    rc = _cmd_generate(Args())
    assert rc == 0
    assert out_path.is_file()
    parsed = json.loads(out_path.read_text(encoding="utf-8"))
    assert parsed["openapi"].startswith("3.")
    assert "paths" in parsed


def test_cmd_generate_creates_parent_directories(tmp_path: Path) -> None:
    out_path = tmp_path / "nested" / "deep" / "spec.json"

    class Args:
        out = str(out_path)

    rc = _cmd_generate(Args())
    assert rc == 0
    assert out_path.is_file()


def test_cmd_generate_overwrites_existing(tmp_path: Path) -> None:
    out_path = tmp_path / "spec.json"
    out_path.write_text('{"stale": true}', encoding="utf-8")

    class Args:
        out = str(out_path)

    rc = _cmd_generate(Args())
    assert rc == 0
    parsed = json.loads(out_path.read_text(encoding="utf-8"))
    assert "stale" not in parsed
    assert "openapi" in parsed


# ---------------------------------------------------------------------------
# _cmd_diff exit codes
# ---------------------------------------------------------------------------


def test_cmd_diff_returns_zero_on_match(tmp_path: Path) -> None:
    """Generate then immediately diff -- must match."""
    out_path = tmp_path / "spec.json"

    class GenArgs:
        out = str(out_path)

    _cmd_generate(GenArgs())

    class DiffArgs:
        artifact = str(out_path)

    rc = _cmd_diff(DiffArgs())
    assert rc == 0


def test_cmd_diff_returns_two_on_drift_path_added(
    tmp_path: Path, capsys
) -> None:
    """Stale committed file (missing routes) -> drift detected."""
    out_path = tmp_path / "spec.json"
    stale = {
        "openapi": "3.1.0",
        "info": {"title": "stale", "version": "0.0.1"},
        "paths": {},  # missing all routes
    }
    out_path.write_text(json.dumps(stale, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")

    class DiffArgs:
        artifact = str(out_path)

    rc = _cmd_diff(DiffArgs())
    assert rc == 2
    captured = capsys.readouterr()
    assert "DRIFT DETECTED" in captured.err
    assert "routes added" in captured.err


def test_cmd_diff_returns_two_on_drift_path_removed(
    tmp_path: Path, capsys
) -> None:
    """Committed file with EXTRA routes that the live spec doesn't have."""
    out_path = tmp_path / "spec.json"
    bloated = {
        "openapi": "3.1.0",
        "info": {"title": "bloated", "version": "0.0.1"},
        "paths": {
            "/healthz": {},
            "/imaginary/route": {},
        },
    }
    out_path.write_text(json.dumps(bloated, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")

    class DiffArgs:
        artifact = str(out_path)

    rc = _cmd_diff(DiffArgs())
    assert rc == 2
    captured = capsys.readouterr()
    assert "routes removed" in captured.err
    assert "imaginary" in captured.err


def test_cmd_diff_detects_body_only_change(tmp_path: Path, capsys) -> None:
    """Same path set but different schema bodies -> drift detected with
    body-only message."""
    out_path = tmp_path / "spec.json"
    live = _generate_live_schema()
    # Same paths but mutated info.version
    tampered = json.loads(json.dumps(live))  # deep copy
    tampered["info"]["version"] = "9.9.9-tampered"
    out_path.write_text(
        json.dumps(tampered, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    class DiffArgs:
        artifact = str(out_path)

    rc = _cmd_diff(DiffArgs())
    assert rc == 2
    captured = capsys.readouterr()
    assert "no path-set changes" in captured.err


def test_cmd_diff_returns_one_on_missing_artifact(
    tmp_path: Path, capsys
) -> None:
    class DiffArgs:
        artifact = str(tmp_path / "does-not-exist.json")

    rc = _cmd_diff(DiffArgs())
    assert rc == 1
    captured = capsys.readouterr()
    assert "ERROR" in captured.err


# ---------------------------------------------------------------------------
# _cmd_show
# ---------------------------------------------------------------------------


def test_cmd_show_prints_metadata(capsys) -> None:
    class Args:
        verbose = False

    rc = _cmd_show(Args())
    assert rc == 0
    captured = capsys.readouterr()
    assert "openapi:" in captured.out
    assert "title:" in captured.out
    assert "paths:" in captured.out


def test_cmd_show_verbose_lists_paths(capsys) -> None:
    class Args:
        verbose = True

    rc = _cmd_show(Args())
    assert rc == 0
    captured = capsys.readouterr()
    # Verbose output should include at least one full path with methods
    assert "/healthz" in captured.out
    # Methods rendered like "[get]"
    assert "get" in captured.out


# ---------------------------------------------------------------------------
# CLI argparse + main exit codes
# ---------------------------------------------------------------------------


def test_build_parser_requires_subcommand() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args([])


def test_build_parser_generate_defaults() -> None:
    p = build_parser()
    ns = p.parse_args(["generate"])
    assert ns.out == _DEFAULT_ARTIFACT


def test_build_parser_diff_defaults() -> None:
    p = build_parser()
    ns = p.parse_args(["diff"])
    assert ns.artifact == _DEFAULT_ARTIFACT


def test_build_parser_show_verbose_flag() -> None:
    p = build_parser()
    ns_quiet = p.parse_args(["show"])
    assert ns_quiet.verbose is False
    ns_verbose = p.parse_args(["show", "--verbose"])
    assert ns_verbose.verbose is True


def test_main_generate_then_diff_round_trip(tmp_path: Path) -> None:
    """Generate followed by diff must report no drift -- the canonical
    workflow for an SDK pipeline."""
    out_path = tmp_path / "spec.json"
    assert main(["generate", "--out", str(out_path)]) == 0
    assert main(["diff", "--artifact", str(out_path)]) == 0


def test_main_show_returns_zero() -> None:
    assert main(["show"]) == 0


def test_main_show_verbose_returns_zero() -> None:
    assert main(["show", "--verbose"]) == 0


# ---------------------------------------------------------------------------
# Pinning tests for the committed docs/openapi.json artifact
# ---------------------------------------------------------------------------


def test_committed_artifact_exists_and_is_canonical() -> None:
    """docs/openapi.json MUST exist + match the live schema. If this
    fails the artifact is stale and CI should reject the merge."""
    artifact = _REPO_ROOT / "docs" / "openapi.json"
    assert artifact.is_file(), (
        f"docs/openapi.json missing at {artifact}; run "
        f"`python -m tools.openapi_export generate` and commit."
    )
    committed = artifact.read_text(encoding="utf-8")
    live = _normalise(_generate_live_schema())
    assert committed == live, (
        "docs/openapi.json drift detected. Run "
        "`python -m tools.openapi_export generate` and commit."
    )


def test_committed_artifact_has_v1_control_routes() -> None:
    """High-level pinning: every CP-46..CP-49 wired route MUST appear in
    the committed schema."""
    artifact = _REPO_ROOT / "docs" / "openapi.json"
    spec = json.loads(artifact.read_text(encoding="utf-8"))
    paths = spec["paths"]
    required = [
        "/v1/control/workflows",
        "/v1/control/agents",
        "/v1/control/tools",
        "/v1/control/audit",
        "/v1/control/replay",
        "/v1/control/dossier",
        "/v1/control/dossier/{dossier_id}",
        "/v1/control/policy/bundles",
        "/v1/control/policy/bundles/{name}",
        "/v1/control/webhooks/subscriptions",
        "/v1/control/webhooks/deliveries",
    ]
    missing = [p for p in required if p not in paths]
    assert not missing, f"committed schema missing routes: {missing}"
