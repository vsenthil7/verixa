"""CP-59 tests for the .github/workflows/release.yml SDK release workflow.

Closes the GitHub-Actions release-workflow blocker flagged in
CP-55/CP-56/CP-58 commit messages. The workflow file is verified
structurally (YAML parses, expected jobs present, OIDC permissions
set, environments named correctly) so a future contributor cannot
accidentally remove the permissions block (which would silently break
trusted-publisher OIDC) or drop a job.

This tests the WORKFLOW DEFINITION, not the workflow execution -- a
real publish test would need PyPI/npm staging accounts. The structural
asserts cover the failure modes that have bitten other projects:

  - Forgetting id-token: write breaks OIDC
  - Forgetting --provenance breaks SLSA chain on npm
  - Forgetting environment: pins breaks PyPI trusted-publisher
  - Forgetting if: github.event_name == 'push' would publish on every
    workflow_dispatch dry-run (catastrophic)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "release.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    raw = _WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    return data


# ---------------------------------------------------------------------------
# Existence + parse
# ---------------------------------------------------------------------------


def test_release_workflow_exists() -> None:
    assert _WORKFLOW.is_file(), (
        f"release workflow missing at {_WORKFLOW}; SDK publish pipeline broken."
    )


def test_release_workflow_yaml_parses(workflow: dict) -> None:
    assert isinstance(workflow, dict)
    assert workflow["name"] == "release"


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------


def test_triggers_on_v_tag_push(workflow: dict) -> None:
    """The canonical SDK trigger is a `v*` git tag (e.g. v0.1.0).
    Pushing to a branch must NOT trigger publish."""
    # PyYAML reads `on:` as Python boolean True
    triggers = workflow[True]
    assert "push" in triggers
    assert "tags" in triggers["push"]
    assert "v*" in triggers["push"]["tags"]


def test_triggers_supports_workflow_dispatch_dry_run(workflow: dict) -> None:
    """The Actions tab manual button must allow a dry-run (build+test
    without publishing) so we can shake out workflow bugs before tagging."""
    triggers = workflow[True]
    assert "workflow_dispatch" in triggers


def test_workflow_dispatch_has_dry_run_input(workflow: dict) -> None:
    triggers = workflow[True]
    dispatch = triggers["workflow_dispatch"]
    assert "inputs" in dispatch
    assert "dry_run" in dispatch["inputs"]
    assert dispatch["inputs"]["dry_run"]["default"] is True, (
        "dry_run default MUST be True so manual runs don't accidentally publish"
    )


# ---------------------------------------------------------------------------
# Concurrency -- never cancel a release in flight
# ---------------------------------------------------------------------------


def test_concurrency_does_not_cancel_in_progress(workflow: dict) -> None:
    """A release midway through publish-pypi MUST NOT be cancelled by a
    newer tag push -- you'd end up with a published Python package and
    no npm package, which is worse than either failure mode alone."""
    concur = workflow["concurrency"]
    assert concur["cancel-in-progress"] is False


# ---------------------------------------------------------------------------
# Jobs structure
# ---------------------------------------------------------------------------


def test_all_expected_jobs_present(workflow: dict) -> None:
    """The pipeline has 6 jobs in a specific dependency order."""
    expected = {
        "verify",
        "build-python",
        "build-npm",
        "publish-pypi",
        "publish-npm",
        "github-release",
    }
    assert set(workflow["jobs"].keys()) == expected


def test_build_jobs_depend_on_verify(workflow: dict) -> None:
    """Building artifacts before tests pass is a footgun -- pin the
    dependency."""
    assert workflow["jobs"]["build-python"]["needs"] == "verify"
    assert workflow["jobs"]["build-npm"]["needs"] == "verify"


def test_publish_jobs_depend_on_both_builds(workflow: dict) -> None:
    """Publishing one artifact without the other is the worst outcome --
    pin both publish jobs to wait for both builds."""
    for job_name in ("publish-pypi", "publish-npm"):
        needs = workflow["jobs"][job_name]["needs"]
        assert "build-python" in needs
        assert "build-npm" in needs


def test_github_release_depends_on_both_publishes(workflow: dict) -> None:
    """GitHub Release runs LAST -- it announces what has already been
    published; publishing failure must block the release notes."""
    needs = workflow["jobs"]["github-release"]["needs"]
    assert "publish-pypi" in needs
    assert "publish-npm" in needs


# ---------------------------------------------------------------------------
# Publish jobs: only run on real tag push, not on dispatch
# ---------------------------------------------------------------------------


def test_publish_jobs_gated_on_push_event(workflow: dict) -> None:
    """publish-pypi + publish-npm + github-release MUST be conditioned on
    github.event_name == 'push' so workflow_dispatch dry-runs don't
    accidentally publish."""
    for job_name in ("publish-pypi", "publish-npm", "github-release"):
        condition = workflow["jobs"][job_name].get("if", "")
        assert "github.event_name == 'push'" in condition, (
            f"Job {job_name} missing publish-gate condition; "
            f"dry-run would publish for real!"
        )


# ---------------------------------------------------------------------------
# OIDC permissions (PyPI trusted publisher + npm provenance)
# ---------------------------------------------------------------------------


def test_pypi_publish_has_id_token_write(workflow: dict) -> None:
    """PyPI trusted publisher needs `id-token: write` to mint the OIDC
    token GitHub presents to PyPI. Without this the publish silently
    falls back to looking for a PYPI_API_TOKEN secret + fails."""
    perms = workflow["jobs"]["publish-pypi"]["permissions"]
    assert perms["id-token"] == "write"


def test_npm_publish_has_id_token_write(workflow: dict) -> None:
    """npm --provenance requires `id-token: write` to attest the build
    came from this repo + commit per SLSA."""
    perms = workflow["jobs"]["publish-npm"]["permissions"]
    assert perms["id-token"] == "write"


def test_npm_publish_uses_provenance_flag(workflow: dict) -> None:
    """The publish step MUST pass --provenance so the published package
    has a SLSA build provenance attestation on the npm registry."""
    publish_step = next(
        s
        for s in workflow["jobs"]["publish-npm"]["steps"]
        if s.get("name") == "Publish with provenance"
    )
    assert "--provenance" in publish_step["run"]
    assert "--access public" in publish_step["run"]


# ---------------------------------------------------------------------------
# Environments (PyPI trusted-publisher requirement)
# ---------------------------------------------------------------------------


def test_pypi_publish_uses_release_environment(workflow: dict) -> None:
    """PyPI trusted-publisher pairs (repo, workflow, environment) at
    https://pypi.org/manage/account/publishing/ -- the environment name
    here MUST match what's configured on PyPI's side."""
    env = workflow["jobs"]["publish-pypi"]["environment"]
    assert env["name"] == "release-pypi"
    assert "pypi.org/project/verixa" in env["url"]


def test_npm_publish_uses_release_environment(workflow: dict) -> None:
    env = workflow["jobs"]["publish-npm"]["environment"]
    assert env["name"] == "release-npm"
    assert "npmjs.com/package/@verixa/ts" in env["url"]


# ---------------------------------------------------------------------------
# Verify job runs the CP-54 OpenAPI drift gate
# ---------------------------------------------------------------------------


def test_verify_runs_openapi_drift_gate(workflow: dict) -> None:
    """The CP-54 drift check MUST run at release time too -- merge-time
    is not enough because a force-push could land a tag on a stale ref."""
    steps = workflow["jobs"]["verify"]["steps"]
    drift_step = next(
        (s for s in steps if "drift" in s.get("name", "").lower()),
        None,
    )
    assert drift_step is not None, "verify job missing OpenAPI drift step"
    assert "openapi_export diff" in drift_step["run"]


def test_verify_runs_pytest_with_coverage(workflow: dict) -> None:
    steps = workflow["jobs"]["verify"]["steps"]
    pytest_step = next(
        (s for s in steps if "pytest" in s.get("name", "").lower()),
        None,
    )
    assert pytest_step is not None
    assert "not integration" in pytest_step["run"]


def test_verify_runs_ruff(workflow: dict) -> None:
    steps = workflow["jobs"]["verify"]["steps"]
    ruff_step = next(
        (s for s in steps if "ruff" in s.get("name", "").lower()),
        None,
    )
    assert ruff_step is not None


def test_verify_runs_ts_typecheck_and_test(workflow: dict) -> None:
    steps = workflow["jobs"]["verify"]["steps"]
    step_names = " ".join(s.get("name", "").lower() for s in steps)
    assert "typecheck" in step_names
    assert "vitest" in step_names


# ---------------------------------------------------------------------------
# Build jobs upload artifacts
# ---------------------------------------------------------------------------


def test_build_python_uploads_dist_artifact(workflow: dict) -> None:
    """Python wheel + sdist must be uploaded as a workflow artifact so
    publish-pypi can download them. Without this the publish job has
    nothing to upload."""
    steps = workflow["jobs"]["build-python"]["steps"]
    upload = next(
        (s for s in steps if "upload" in s.get("name", "").lower()),
        None,
    )
    assert upload is not None
    assert upload["with"]["name"] == "python-dist"


def test_build_npm_uploads_dist_artifact(workflow: dict) -> None:
    steps = workflow["jobs"]["build-npm"]["steps"]
    upload = next(
        (s for s in steps if "upload" in s.get("name", "").lower()),
        None,
    )
    assert upload is not None
    assert upload["with"]["name"] == "npm-dist"


# ---------------------------------------------------------------------------
# Python version + Node version consistent with ci.yml
# ---------------------------------------------------------------------------


def test_python_version_matches_ci(workflow: dict) -> None:
    """release.yml MUST use the same Python version as ci.yml so a
    test that passes on PR doesn't fail at release."""
    ci_path = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
    ci = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    assert workflow["env"]["PYTHON_VERSION"] == ci["env"]["PYTHON_VERSION"]


def test_node_version_matches_ci(workflow: dict) -> None:
    ci_path = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
    ci = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    assert workflow["env"]["NODE_VERSION"] == ci["env"]["NODE_VERSION"]
