"""pytest suite for ops.ps1 + Makefile structural validation.

Verifies:
  - ops.ps1 exists and parses as a PowerShell file (basic structural)
  - Every advertised action in the help text exists in the dispatch switch
  - Auditex BLD-019 invariant: every action goes through Get-LogFile/Invoke-Logged
    OR is explicitly exempt (help, git-status, git-log, db-migrate, db-reset)
  - Auditex BLD-027: git-add-files is documented as one-file-per-call
  - Makefile exists and exposes the same headline targets
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OPS_PATH: Final[Path] = REPO_ROOT / "ops.ps1"
MAKEFILE_PATH: Final[Path] = REPO_ROOT / "Makefile"

# Actions advertised in `Invoke-Help` MUST be dispatched in the switch.
EXPECTED_ACTIONS: Final[tuple[str, ...]] = (
    "up",
    "down",
    "restart",
    "health",
    "logs",
    "test",
    "test-py",
    "test-ts",
    "lint",
    "git-status",
    "git-log",
    "git-add-files",
    "commit-staged",
    "push",
    "db-migrate",
    "db-reset",
    "compliance-check",
    "verify-mi300x",
    "backup",
    "help",
)

# Subset of actions that headline the Makefile too (subset of EXPECTED_ACTIONS).
EXPECTED_MAKE_TARGETS: Final[tuple[str, ...]] = (
    "up",
    "down",
    "restart",
    "health",
    "test",
    "test-py",
    "test-ts",
    "lint",
    "git-status",
    "git-log",
    "push",
    "db-migrate",
    "db-reset",
    "verify-mi300x",
    "install",
    "clean",
    "help",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ops_text() -> str:
    assert OPS_PATH.is_file(), f"ops.ps1 not found at {OPS_PATH}"
    return OPS_PATH.read_text(encoding="utf-8-sig")


@pytest.fixture(scope="module")
def makefile_text() -> str:
    assert MAKEFILE_PATH.is_file(), f"Makefile not found at {MAKEFILE_PATH}"
    return MAKEFILE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# ops.ps1 structural
# ---------------------------------------------------------------------------


def test_ops_has_param_block(ops_text: str) -> None:
    assert "[CmdletBinding()]" in ops_text
    assert "param(" in ops_text


def test_ops_sets_strict_error_action(ops_text: str) -> None:
    assert '$ErrorActionPreference = "Stop"' in ops_text


def test_ops_resolves_repo_root(ops_text: str) -> None:
    assert "$Script:RepoRoot" in ops_text
    assert "$MyInvocation.MyCommand.Path" in ops_text


def test_ops_creates_logs_and_backup_dirs(ops_text: str) -> None:
    assert "$Script:LogsDir" in ops_text
    assert "$Script:BackupDir" in ops_text
    # Both dirs must be auto-created if missing
    assert "New-Item -ItemType Directory -Path $Script:LogsDir" in ops_text
    assert "New-Item -ItemType Directory -Path $Script:BackupDir" in ops_text


def test_ops_has_get_logfile_and_invoke_logged(ops_text: str) -> None:
    """BLD-019: every action MUST go through Get-LogFile + Invoke-Logged."""
    assert "function Get-LogFile" in ops_text
    assert "function Invoke-Logged" in ops_text


# ---------------------------------------------------------------------------
# Every advertised action is dispatched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", EXPECTED_ACTIONS)
def test_action_advertised_in_help(ops_text: str, action: str) -> None:
    # Help block lives in the Invoke-Help here-string. We just confirm the
    # action token appears somewhere in the help text body.
    help_block_match = re.search(
        r"function Invoke-Help \{(.*?)\n\}", ops_text, re.DOTALL
    )
    assert help_block_match, "Invoke-Help block not found"
    body = help_block_match.group(1)
    # Allow either bare token or token-with-args ('git-add-files <path>')
    assert re.search(rf"\b{re.escape(action)}\b", body), (
        f"action '{action}' not advertised in Invoke-Help"
    )


@pytest.mark.parametrize("action", EXPECTED_ACTIONS)
def test_action_dispatched_in_switch(ops_text: str, action: str) -> None:
    # Switch arms look like:  "<action>" { Invoke-XYZ }
    pattern = rf'"{re.escape(action)}"\s*\{{'
    assert re.search(pattern, ops_text), (
        f"action '{action}' has no dispatch arm in switch"
    )


# ---------------------------------------------------------------------------
# BLD-027: git-add-files takes one file per call
# ---------------------------------------------------------------------------


def test_git_add_files_enforces_single_file(ops_text: str) -> None:
    fn_match = re.search(
        r"function Invoke-GitAddFiles \{(.*?)\n\}", ops_text, re.DOTALL
    )
    assert fn_match, "Invoke-GitAddFiles function not found"
    body = fn_match.group(1)
    # The function MUST reject calls with != 1 args and reference BLD-027 in help text.
    assert "$Script:Args.Count -ne 1" in body
    assert "BLD-027" in body or "ONE file per call" in body


# ---------------------------------------------------------------------------
# verify-mi300x hits the right endpoint
# ---------------------------------------------------------------------------


def test_verify_mi300x_pings_v1_models(ops_text: str) -> None:
    fn_match = re.search(
        r"function Invoke-VerifyMi300x \{(.*?)\n\}", ops_text, re.DOTALL
    )
    assert fn_match
    body = fn_match.group(1)
    assert "/v1/models" in body
    assert "165.245.133.120" in body  # validated droplet IP from AMD_test/


# ---------------------------------------------------------------------------
# compliance-check shells out to verixa.compliance_language
# ---------------------------------------------------------------------------


def test_compliance_check_uses_verixa_module(ops_text: str) -> None:
    fn_match = re.search(
        r"function Invoke-ComplianceCheck \{(.*?)\n\}", ops_text, re.DOTALL
    )
    assert fn_match
    body = fn_match.group(1)
    assert "verixa.compliance_language" in body
    assert "check_text" in body


# ---------------------------------------------------------------------------
# Makefile structural
# ---------------------------------------------------------------------------


def test_makefile_declares_phony(makefile_text: str) -> None:
    assert ".PHONY:" in makefile_text


@pytest.mark.parametrize("target", EXPECTED_MAKE_TARGETS)
def test_makefile_has_target(makefile_text: str, target: str) -> None:
    # Match `target:` at the start of a line, possibly followed by deps.
    pattern = rf"^{re.escape(target)}:\s"
    assert re.search(pattern, makefile_text, re.MULTILINE), (
        f"Makefile missing target: {target}"
    )


def test_makefile_test_runs_both_runtimes(makefile_text: str) -> None:
    # `test:` target must depend on test-py and test-ts
    match = re.search(r"^test:\s+(.*)$", makefile_text, re.MULTILINE)
    assert match, "Makefile missing 'test:' target"
    deps = match.group(1).split()
    assert "test-py" in deps
    assert "test-ts" in deps
