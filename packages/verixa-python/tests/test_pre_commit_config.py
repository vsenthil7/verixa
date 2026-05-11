"""CP-60 tests for .pre-commit-config.yaml structure + drift-gate scope.

Closes the pre-commit-hook blocker flagged in CP-54 commit message. The
config is verified structurally:

  - YAML parses
  - Standard hygiene hooks present (trailing-whitespace, eof-fixer, etc.)
  - Ruff hook present + uses --fix + format
  - The Verixa OpenAPI drift gate is a `local` repo hook that re-runs
    `tools.openapi_export diff` whenever a schema-relevant file changes
  - The drift-gate file regex covers every Python file that could alter
    the FastAPI schema (routes / envelopes / handlers / app / asgi /
    registry / audit) + the committed openapi.json itself

Failure modes guarded:

  - Missing drift hook = devs commit stale openapi.json silently
  - Drift hook missing one of the schema-source files = a route change
    in handlers.py would not trigger re-check
  - pass_filenames true = drift hook gets fed file paths and the CLI
    treats them as arguments instead of running its no-arg diff
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Existence + parse
# ---------------------------------------------------------------------------


def test_pre_commit_config_exists() -> None:
    assert _CONFIG.is_file()


def test_config_yaml_parses(config: dict) -> None:
    assert isinstance(config, dict)
    assert "repos" in config


def test_at_least_three_repo_blocks(config: dict) -> None:
    """Standard hygiene + Ruff + Verixa-local = 3 minimum."""
    assert len(config["repos"]) >= 3


# ---------------------------------------------------------------------------
# Standard hygiene hooks
# ---------------------------------------------------------------------------


def _flatten_hook_ids(config: dict) -> set[str]:
    """All hook IDs across every repo block."""
    out: set[str] = set()
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            out.add(hook["id"])
    return out


@pytest.mark.parametrize(
    "required_id",
    [
        "trailing-whitespace",
        "end-of-file-fixer",
        "check-yaml",
        "check-toml",
        "check-json",
        "check-added-large-files",
        "check-merge-conflict",
    ],
)
def test_standard_hygiene_hook_present(config: dict, required_id: str) -> None:
    """7 hygiene hooks from pre-commit/pre-commit-hooks. If a future
    contributor removes one of these silently, the hook gate weakens."""
    assert required_id in _flatten_hook_ids(config)


def test_large_file_threshold_reasonable(config: dict) -> None:
    """The maxkb threshold prevents committing huge binaries by accident.
    docs/openapi.json is ~22KB; SBOM is ~201KB. 512KB is comfortable."""
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            if hook["id"] == "check-added-large-files":
                args = hook.get("args", [])
                threshold_arg = next(
                    (a for a in args if a.startswith("--maxkb=")),
                    None,
                )
                assert threshold_arg is not None
                value = int(threshold_arg.split("=")[1])
                assert 256 <= value <= 1024


# ---------------------------------------------------------------------------
# Ruff hook
# ---------------------------------------------------------------------------


def test_ruff_hook_present(config: dict) -> None:
    """The repo uses ruff for lint + format; pre-commit must run both."""
    hook_ids = _flatten_hook_ids(config)
    assert "ruff" in hook_ids
    assert "ruff-format" in hook_ids


def test_ruff_hook_uses_fix(config: dict) -> None:
    """`--fix` makes ruff auto-correct what it can on commit, which is
    the whole point of running it as a hook (vs CI-only where you would
    want fail-without-fix)."""
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            if hook["id"] == "ruff":
                assert "--fix" in hook.get("args", [])
                return
    pytest.fail("ruff hook not found")


def test_ruff_repo_pinned_to_specific_version(config: dict) -> None:
    """Hook versions MUST be pinned (rev: vX.Y.Z) so a contributor's
    local hook behaviour matches CI's behaviour. Floating refs are
    a common pre-commit footgun."""
    for repo in config["repos"]:
        if "ruff-pre-commit" in repo.get("repo", ""):
            rev = repo["rev"]
            # Must look like vN.N.N (semver) not 'main' or 'HEAD'
            assert re.match(r"^v\d+\.\d+\.\d+$", rev), (
                f"ruff hook rev {rev!r} is not a pinned semver tag"
            )
            return
    pytest.fail("ruff-pre-commit repo not configured")


# ---------------------------------------------------------------------------
# OpenAPI drift gate (CP-54)
# ---------------------------------------------------------------------------


def _find_drift_hook(config: dict) -> dict | None:
    for repo in config["repos"]:
        if repo.get("repo") == "local":
            for hook in repo.get("hooks", []):
                if hook.get("id") == "openapi-drift":
                    return hook
    return None


def test_openapi_drift_hook_present(config: dict) -> None:
    hook = _find_drift_hook(config)
    assert hook is not None, (
        "openapi-drift hook missing; CP-54 drift gate not enforced locally"
    )


def test_openapi_drift_uses_cp54_cli(config: dict) -> None:
    """The hook MUST invoke `tools.openapi_export diff` -- the CP-54 CLI
    that already returns exit 2 on drift."""
    hook = _find_drift_hook(config)
    assert hook is not None
    assert "openapi_export" in hook["entry"]
    assert "diff" in hook["entry"]


def test_openapi_drift_pass_filenames_is_false(config: dict) -> None:
    """If pass_filenames=true (the default), pre-commit feeds the
    changed-file paths as positional args to the CLI -- which would
    break our argparse (the CLI's `diff` subcommand takes no positional
    args, only --artifact)."""
    hook = _find_drift_hook(config)
    assert hook is not None
    assert hook.get("pass_filenames") is False


def test_openapi_drift_uses_language_system(config: dict) -> None:
    """We use `language: system` so the hook runs in the dev's existing
    Poetry env (where tools.openapi_export is importable). The default
    `python` language would create a fresh venv per hook run -- slow."""
    hook = _find_drift_hook(config)
    assert hook is not None
    assert hook.get("language") == "system"


@pytest.mark.parametrize(
    "schema_source",
    [
        "apps/control-plane-api/verixa_control_plane/routes.py",
        "apps/control-plane-api/verixa_control_plane/envelopes.py",
        "apps/control-plane-api/verixa_control_plane/handlers.py",
        "apps/control-plane-api/verixa_control_plane/audit.py",
        "apps/control-plane-api/verixa_control_plane/app.py",
        "apps/control-plane-api/verixa_control_plane/asgi.py",
        "apps/control-plane-api/verixa_control_plane/registry.py",
        "docs/openapi.json",
    ],
)
def test_drift_hook_covers_schema_source(config: dict, schema_source: str) -> None:
    """Every file that COULD alter the FastAPI schema MUST trigger the
    drift hook. If a file is missing from the regex, a route change
    there would slip past local enforcement (CI still catches it via
    release.yml, but the dev would only learn at PR time)."""
    hook = _find_drift_hook(config)
    assert hook is not None
    pattern = hook["files"]
    compiled = re.compile(pattern, re.VERBOSE)
    assert compiled.match(schema_source), (
        f"drift-hook files regex does not match {schema_source!r}; "
        f"route changes there would bypass the local gate."
    )


def test_drift_hook_does_not_match_unrelated_files(config: dict) -> None:
    """The regex must be specific -- matching every Python file would
    re-run the drift check on every commit + slow developer workflow."""
    hook = _find_drift_hook(config)
    assert hook is not None
    pattern = hook["files"]
    compiled = re.compile(pattern, re.VERBOSE)
    # These files MUST NOT trigger the drift gate
    for unrelated in (
        "README.md",
        "packages/verixa-python/verixa/sdk.py",
        "packages/verixa-ts/src/sdk.ts",
        "tools/timing_benchmark.py",
        "policies/core/pii_redaction.rego",
    ):
        assert not compiled.match(unrelated), (
            f"drift hook over-matches {unrelated!r}; would slow commits."
        )


def test_check_json_excludes_openapi_artifact(config: dict) -> None:
    r"""check-json must NOT validate docs/openapi.json -- if it did, the
    drift hook would never get to run because check-json runs first +
    might pass on stale-but-valid JSON, masking the drift signal.

    The exclude is a regex; we compile it and assert it matches the
    actual artifact path (the escaped form openapi\.json must work
    against the unescaped path docs/openapi.json)."""
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            if hook["id"] == "check-json":
                exclude = hook.get("exclude", "")
                compiled = re.compile(exclude)
                assert compiled.match("docs/openapi.json"), (
                    f"check-json exclude regex {exclude!r} does not "
                    f"match docs/openapi.json; the drift hook would "
                    f"not be the authoritative gate."
                )
                return
    pytest.fail("check-json hook not found")
