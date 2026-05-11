"""CP-55 tests for verixa Python SDK PyPI publish-readiness.

Anchored to Phase-1 carry-forward "verixa-python SDK to PyPI publish".
This file pins the package surface that customer SDK pipelines depend on:

  - py.typed marker is present (PEP 561; downstream type checkers honor it)
  - README.md exists + mentions every documented resource client
  - CHANGELOG.md exists in Keep-a-Changelog format with v0.1.0 entry
  - __version__ matches CHANGELOG header (single source of truth)
  - All advertised public symbols in __all__ are importable
  - Resource client method names match what README documents
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# PEP 561 py.typed marker
# ---------------------------------------------------------------------------


def test_py_typed_marker_exists() -> None:
    """PEP 561 says: ship a `py.typed` file inside the importable package
    for type checkers to honor inline type annotations."""
    marker = _PACKAGE_ROOT / "verixa" / "py.typed"
    assert marker.is_file(), (
        f"py.typed marker missing at {marker}; required for PEP 561."
    )


def test_py_typed_marker_is_empty() -> None:
    """PEP 561 specifies the marker file is conventionally empty (its
    PRESENCE is what signals 'typed', not its content)."""
    marker = _PACKAGE_ROOT / "verixa" / "py.typed"
    assert marker.stat().st_size == 0


# ---------------------------------------------------------------------------
# README.md
# ---------------------------------------------------------------------------


def test_readme_exists() -> None:
    assert (_PACKAGE_ROOT / "README.md").is_file()


def test_readme_documents_install_command() -> None:
    readme = (_PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")
    assert "pip install verixa" in readme


def test_readme_documents_python_version_requirement() -> None:
    """v0.1.0 SDK targets Python 3.12+. README must say so explicitly so
    pip-install failures on older Pythons are not surprising."""
    readme = (_PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Python 3.12" in readme


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
    """All 8 resource sub-clients MUST appear in the README so customers
    can discover them."""
    readme = (_PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")
    assert client_name in readme, (
        f"README must document `{client_name}` resource client"
    )


def test_readme_documents_exception_classes() -> None:
    readme = (_PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")
    assert "VerixaError" in readme
    assert "VerixaHttpError" in readme
    assert "VerixaConnectionError" in readme


# ---------------------------------------------------------------------------
# CHANGELOG.md
# ---------------------------------------------------------------------------


def test_changelog_exists() -> None:
    assert (_PACKAGE_ROOT / "CHANGELOG.md").is_file()


def test_changelog_has_unreleased_section() -> None:
    """Keep-a-Changelog convention: every CHANGELOG MUST have an
    Unreleased section at the top so the next change has a home before
    cutting a release."""
    changelog = (_PACKAGE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in changelog


def test_changelog_has_v0_1_0_entry() -> None:
    changelog = (_PACKAGE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [0.1.0]" in changelog


def test_changelog_v0_1_0_dated_today() -> None:
    """The v0.1.0 release line carries today's date 2026-05-11."""
    changelog = (_PACKAGE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "[0.1.0] -- 2026-05-11" in changelog or "[0.1.0] - 2026-05-11" in changelog


def test_changelog_documents_known_limitations() -> None:
    """Phase-0 alpha limitations MUST be documented so customers know
    what to expect."""
    changelog = (_PACKAGE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Limitations" in changelog
    # Must mention each known v0.1.0 limitation
    assert "dict" in changelog  # plain dicts not Pydantic models
    assert "retry" in changelog  # no automatic retry
    assert "sync" in changelog or "synchronous" in changelog  # no sync wrapper


# ---------------------------------------------------------------------------
# __version__ matches CHANGELOG header
# ---------------------------------------------------------------------------


def test_package_version_matches_changelog_latest_release() -> None:
    """__version__ must match the most recent dated release in
    CHANGELOG.md; otherwise a customer reading the changelog might
    think they have a different version than they actually do."""
    import verixa

    changelog = (_PACKAGE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # First "## [x.y.z]" line that has a date next to it
    m = re.search(r"##\s+\[(\d+\.\d+\.\d+)\]\s+-+\s+\d{4}-\d{2}-\d{2}", changelog)
    assert m is not None, "CHANGELOG has no dated release header"
    assert verixa.__version__ == m.group(1), (
        f"__version__ {verixa.__version__} != latest CHANGELOG release "
        f"{m.group(1)}; update one to match the other."
    )


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_top_level_imports_resolve() -> None:
    """Every advertised symbol in `from verixa import ...` MUST exist."""
    from verixa import (  # noqa: F401
        AgentsClient,
        AuditClient,
        BundlesClient,
        DossierClient,
        ReplayClient,
        ToolsClient,
        VerixaClient,
        VerixaConnectionError,
        VerixaError,
        VerixaHttpError,
        WebhooksClient,
        WorkflowsClient,
    )


def test_all_lists_match_advertised_symbols() -> None:
    """The __all__ list pins the wildcard-import surface.

    CP-61 added 6 envelope dataclass exports;
    CP-62 added 2 more (AgentRegisterResponse + ToolRegisterResponse)."""
    import verixa

    expected = {
        # Resource clients (8) + base client (1) + exceptions (3) = 12 (CP-50)
        "AgentsClient",
        "AuditClient",
        "BundlesClient",
        "DossierClient",
        "ReplayClient",
        "ToolsClient",
        "VerixaClient",
        "VerixaConnectionError",
        "VerixaError",
        "VerixaHttpError",
        "WebhooksClient",
        "WorkflowsClient",
        # Typed envelope dataclasses (6) added by CP-61
        "AuditEntry",
        "AuditQueryResponse",
        "InvalidEnvelopeError",
        "WorkflowListResponse",
        "WorkflowRegisterResponse",
        "WorkflowSummary",
        # Typed envelope dataclasses (2 more) added by CP-62
        "AgentRegisterResponse",
        "ToolRegisterResponse",
    }
    assert set(verixa.__all__) == expected


# ---------------------------------------------------------------------------
# Resource client method names match what README documents
# ---------------------------------------------------------------------------


def test_workflows_client_has_register_and_list() -> None:
    from verixa import WorkflowsClient

    assert callable(getattr(WorkflowsClient, "register", None))
    assert callable(getattr(WorkflowsClient, "list", None))


def test_bundles_client_has_list_and_fetch() -> None:
    from verixa import BundlesClient

    assert callable(getattr(BundlesClient, "list", None))
    assert callable(getattr(BundlesClient, "fetch", None))


def test_webhooks_client_has_three_methods() -> None:
    from verixa import WebhooksClient

    for name in ("subscribe", "list_subscriptions", "recent_deliveries"):
        assert callable(getattr(WebhooksClient, name, None)), (
            f"WebhooksClient.{name} missing"
        )


def test_dossier_client_has_generate_and_get() -> None:
    from verixa import DossierClient

    for name in ("generate", "get"):
        assert callable(getattr(DossierClient, name, None))
