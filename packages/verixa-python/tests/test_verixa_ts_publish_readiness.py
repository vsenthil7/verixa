"""CP-56 tests for @verixa/ts npm publish-readiness.

Anchored to Phase-1 carry-forward "verixa-ts SDK to npm publish". Mirrors
CP-55 for the TypeScript SDK: tests pin the README + CHANGELOG + package.json
metadata to the actual code surface so they cannot drift silently.

Tests run in pytest (the project's primary test runner) and READ the
TypeScript package files as plain text. Test names mirror the Python
publish-readiness suite for symmetry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TS_PACKAGE = _REPO_ROOT / "packages" / "verixa-ts"


# ---------------------------------------------------------------------------
# README.md
# ---------------------------------------------------------------------------


def test_readme_exists() -> None:
    assert (_TS_PACKAGE / "README.md").is_file()


def test_readme_documents_npm_install() -> None:
    readme = (_TS_PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "npm install @verixa/ts" in readme


def test_readme_documents_node_version_requirement() -> None:
    """v0.1.0 SDK targets Node 20+ (uses built-in fetch)."""
    readme = (_TS_PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "Node 20" in readme


def test_readme_documents_zero_dependencies() -> None:
    """A selling point: no runtime deps. Must be advertised so customers
    notice and prefer it over heavier SDKs."""
    readme = (_TS_PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "No runtime dependencies" in readme


@pytest.mark.parametrize(
    "client_name",
    [
        ".workflows",
        ".agents",
        ".tools",
        ".audit",
        ".replay",
        ".dossier",
        ".bundles",
        ".webhooks",
    ],
)
def test_readme_documents_each_resource_client(client_name: str) -> None:
    """All 8 resource sub-clients MUST appear in the README."""
    readme = (_TS_PACKAGE / "README.md").read_text(encoding="utf-8")
    assert client_name in readme


def test_readme_documents_exception_classes() -> None:
    readme = (_TS_PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "VerixaError" in readme
    assert "VerixaHttpError" in readme
    assert "VerixaConnectionError" in readme


def test_readme_documents_camelcase_method_args() -> None:
    """The README MUST explain that args are camelCase TypeScript objects
    mapped to snake_case wire format (otherwise customers will type
    workflow_id and be surprised)."""
    readme = (_TS_PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "camelCase" in readme
    assert "snake_case" in readme


# ---------------------------------------------------------------------------
# CHANGELOG.md
# ---------------------------------------------------------------------------


def test_changelog_exists() -> None:
    assert (_TS_PACKAGE / "CHANGELOG.md").is_file()


def test_changelog_has_unreleased_section() -> None:
    changelog = (_TS_PACKAGE / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in changelog


def test_changelog_has_v0_1_0_entry() -> None:
    changelog = (_TS_PACKAGE / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [0.1.0]" in changelog


def test_changelog_v0_1_0_dated_today() -> None:
    changelog = (_TS_PACKAGE / "CHANGELOG.md").read_text(encoding="utf-8")
    assert (
        "[0.1.0] -- 2026-05-11" in changelog
        or "[0.1.0] - 2026-05-11" in changelog
    )


def test_changelog_documents_zero_dependencies() -> None:
    changelog = (_TS_PACKAGE / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "zero runtime dependencies" in changelog.lower()


def test_changelog_documents_known_limitations() -> None:
    changelog = (_TS_PACKAGE / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Limitations" in changelog


# ---------------------------------------------------------------------------
# package.json npm publish metadata
# ---------------------------------------------------------------------------


def test_package_json_exists_and_parses() -> None:
    raw = (_TS_PACKAGE / "package.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["name"] == "@verixa/ts"


def test_package_json_has_required_npm_metadata() -> None:
    """Every npm-published package SHOULD have these fields per the npm
    docs; without them the package looks unprofessional + customers
    cannot find the repo / report bugs."""
    parsed = json.loads((_TS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    for required in (
        "name",
        "version",
        "description",
        "license",
        "author",
        "homepage",
        "repository",
        "bugs",
        "keywords",
        "engines",
    ):
        assert required in parsed, f"package.json missing {required}"


def test_package_json_repository_points_to_github() -> None:
    parsed = json.loads((_TS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert parsed["repository"]["type"] == "git"
    assert "github.com/v-sen/verixa" in parsed["repository"]["url"]
    assert parsed["repository"]["directory"] == "packages/verixa-ts"


def test_package_json_engines_pins_node_20_plus() -> None:
    """The README says Node 20+; the package.json engines field MUST
    enforce this so npm warns customers using older Node."""
    parsed = json.loads((_TS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert parsed["engines"]["node"] == ">=20"


def test_package_json_keywords_help_discoverability() -> None:
    """npm search uses keywords; this is non-negotiable for SEO."""
    parsed = json.loads((_TS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    keywords = parsed["keywords"]
    assert "verixa" in keywords
    assert "sdk" in keywords
    # At least 5 keywords (cap at ~10 to keep meaningful)
    assert 5 <= len(keywords) <= 12


def test_package_json_files_includes_readme_and_changelog() -> None:
    """The npm-published tarball MUST include README + CHANGELOG +
    LICENSE so customers reading docs at the npm page see them."""
    parsed = json.loads((_TS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    files = parsed["files"]
    assert "README.md" in files
    assert "CHANGELOG.md" in files
    assert "LICENSE" in files
    assert "dist" in files  # the compiled output


def test_package_json_exposes_sdk_export() -> None:
    """The sdk subpath export must be present so customers can do
    `import { ... } from '@verixa/ts/sdk'` if they want narrower imports."""
    parsed = json.loads((_TS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "./sdk" in parsed["exports"]


def test_package_json_version_matches_changelog_release() -> None:
    """package.json version must match the most recent dated CHANGELOG
    release header."""
    parsed = json.loads((_TS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    changelog = (_TS_PACKAGE / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"##\s+\[(\d+\.\d+\.\d+)\]\s+-+\s+\d{4}-\d{2}-\d{2}", changelog)
    assert m is not None
    assert parsed["version"] == m.group(1), (
        f"package.json version {parsed['version']} != latest CHANGELOG "
        f"release {m.group(1)}; update one to match the other."
    )


def test_package_json_version_matches_user_agent_string() -> None:
    """The version in package.json MUST match the version embedded in the
    User-Agent header by VerixaClient (verixa-ts/0.1.0). Otherwise
    customers reading their server logs will see a version that does not
    correspond to what's installed."""
    parsed = json.loads((_TS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    sdk_src = (_TS_PACKAGE / "src" / "sdk.ts").read_text(encoding="utf-8")
    expected_ua = f"verixa-ts/{parsed['version']}"
    assert expected_ua in sdk_src, (
        f"package.json version {parsed['version']} but SDK User-Agent "
        f"string {expected_ua!r} not found in sdk.ts"
    )


def test_package_json_license_is_mit() -> None:
    parsed = json.loads((_TS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert parsed["license"] == "MIT"


# ---------------------------------------------------------------------------
# Pinning: the SDK ts source documents all 8 resource clients
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "client_class",
    [
        "WorkflowsClient",
        "AgentsClient",
        "ToolsClient",
        "AuditClient",
        "ReplayClient",
        "DossierClient",
        "BundlesClient",
        "WebhooksClient",
    ],
)
def test_sdk_ts_exports_resource_client(client_class: str) -> None:
    """The 8 resource classes in sdk.ts must remain exported so the
    public-API surface stays stable."""
    sdk_src = (_TS_PACKAGE / "src" / "sdk.ts").read_text(encoding="utf-8")
    assert f"export class {client_class}" in sdk_src


def test_sdk_ts_exports_exception_classes() -> None:
    """The 3 exception classes must remain exported."""
    sdk_src = (_TS_PACKAGE / "src" / "sdk.ts").read_text(encoding="utf-8")
    for cls in ("VerixaError", "VerixaHttpError", "VerixaConnectionError"):
        assert f"export class {cls}" in sdk_src
