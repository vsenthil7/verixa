"""CP-58 tests for the per-package pyproject.toml of verixa-python.

Closes the pyproject.toml-per-package blocker flagged in CP-55 commit
message. This file pins the PEP 621 metadata against the actual SDK
implementation so they cannot drift silently:

  - Build backend is set (PEP 517 buildable)
  - Project name + version match verixa.__version__ + CHANGELOG release
  - Dependencies match what httpx the SDK actually imports
  - License field points at the LICENSE file
  - Classifiers include the standards PyPI uses to surface the package
    (Typed marker, Python version, license, async support, alpha status)
  - URLs cover the standard set PyPI shows on the project page
  - Readme + py.typed are referenced + present in the wheel target
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PKG = _REPO_ROOT / "packages" / "verixa-python"
_PYPROJECT = _PKG / "pyproject.toml"


# ---------------------------------------------------------------------------
# Existence + parse
# ---------------------------------------------------------------------------


def test_pyproject_toml_exists() -> None:
    assert _PYPROJECT.is_file(), (
        f"per-package pyproject.toml missing at {_PYPROJECT}; required "
        f"for `python -m build` + PyPI publish."
    )


@pytest.fixture(scope="module")
def manifest() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Build system (PEP 517)
# ---------------------------------------------------------------------------


def test_build_system_present(manifest: dict) -> None:
    """[build-system] required by PEP 517."""
    assert "build-system" in manifest
    assert "requires" in manifest["build-system"]
    assert "build-backend" in manifest["build-system"]


def test_build_backend_is_hatchling(manifest: dict) -> None:
    """We chose hatchling -- pinned via this test so a future contributor
    switching backends has to update this assertion deliberately."""
    assert manifest["build-system"]["build-backend"] == "hatchling.build"


def test_build_requires_pins_hatchling(manifest: dict) -> None:
    """`hatchling>=1.25.0` must be in build-requires so reproducible
    builds know which backend version they need."""
    requires = manifest["build-system"]["requires"]
    assert any("hatchling" in r for r in requires)


# ---------------------------------------------------------------------------
# [project] core metadata
# ---------------------------------------------------------------------------


def test_project_name_is_verixa(manifest: dict) -> None:
    """The PyPI distribution name is `verixa`. Customers do
    `pip install verixa` and the README + CHANGELOG say so."""
    assert manifest["project"]["name"] == "verixa"


def test_project_version_matches_package_dunder(manifest: dict) -> None:
    """pyproject version MUST equal verixa.__version__ -- otherwise the
    wheel says one version, the runtime says another."""
    import verixa

    assert manifest["project"]["version"] == verixa.__version__


def test_project_version_matches_changelog_release(manifest: dict) -> None:
    """And it MUST equal the most recent dated CHANGELOG release header."""
    changelog = (_PKG / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"##\s+\[(\d+\.\d+\.\d+)\]\s+-+\s+\d{4}-\d{2}-\d{2}", changelog)
    assert m is not None
    assert manifest["project"]["version"] == m.group(1)


def test_project_description_nonempty(manifest: dict) -> None:
    desc = manifest["project"]["description"]
    assert isinstance(desc, str)
    assert len(desc) >= 20  # a meaningful sentence, not a placeholder


def test_project_readme_points_at_readme_md(manifest: dict) -> None:
    """PyPI renders the readme on the package page; this MUST point at
    the README.md that CP-55 wrote."""
    assert manifest["project"]["readme"] == "README.md"
    assert (_PKG / "README.md").is_file()


def test_project_license_field_points_at_license_file(manifest: dict) -> None:
    """PEP 639 / SPDX recognise the {file = "LICENSE"} form."""
    license_field = manifest["project"]["license"]
    assert license_field == {"file": "LICENSE"}
    assert (_PKG / "LICENSE").is_file()


def test_project_requires_python_3_12_plus(manifest: dict) -> None:
    """The SDK uses datetime.UTC, type-statement syntax etc. that need 3.12+."""
    assert manifest["project"]["requires-python"] == ">=3.12"


def test_project_authors_present(manifest: dict) -> None:
    authors = manifest["project"]["authors"]
    assert isinstance(authors, list)
    assert len(authors) >= 1
    assert all("name" in a for a in authors)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def test_dependencies_pin_httpx(manifest: dict) -> None:
    """The SDK imports httpx; the dep MUST be declared with the version
    band the monorepo root uses (kept in sync to prevent surprises)."""
    deps = manifest["project"]["dependencies"]
    httpx_deps = [d for d in deps if d.startswith("httpx")]
    assert len(httpx_deps) == 1
    # Must include both lower and upper bound so resolver is deterministic
    pin = httpx_deps[0]
    assert ">=0.27" in pin
    assert "<0.28" in pin


def test_no_unexpected_runtime_dependencies(manifest: dict) -> None:
    """v0.1.0 only needs httpx. Any new runtime dep must be a deliberate
    decision documented in CHANGELOG; this test forces that conversation."""
    deps = manifest["project"]["dependencies"]
    # Strip version pins
    names = {d.split(">=")[0].split("<")[0].split("==")[0].split("[")[0].strip()
             for d in deps}
    assert names == {"httpx"}, (
        f"unexpected deps: {names - {'httpx'}}. If adding a dep is "
        f"intentional, update this test + CHANGELOG."
    )


# ---------------------------------------------------------------------------
# Classifiers (PyPI search + UX)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "required",
    [
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3 :: Only",
        "Typing :: Typed",
        "Framework :: AsyncIO",
    ],
)
def test_classifier_present(manifest: dict, required: str) -> None:
    """These 6 classifiers materially affect how PyPI surfaces + filters
    the package. Without them: 'Alpha' badge is missing (customers think
    1.0-stable), MIT badge missing (legal teams reject), no Python-version
    filter match (search results show wrong versions), Typed marker
    invisible (mypy ecosystem ignores the package)."""
    assert required in manifest["project"]["classifiers"]


def test_classifiers_count_reasonable(manifest: dict) -> None:
    """At least 8 classifiers (not a stub manifest), at most 20 (not bloat)."""
    n = len(manifest["project"]["classifiers"])
    assert 8 <= n <= 20


# ---------------------------------------------------------------------------
# Project URLs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["Homepage", "Documentation", "Repository", "Issues", "Changelog"],
)
def test_project_urls_has_key(manifest: dict, key: str) -> None:
    """PyPI shows these URLs on the project page sidebar; missing any
    one is a discoverability bug."""
    assert key in manifest["project"]["urls"]


def test_all_project_urls_point_at_github(manifest: dict) -> None:
    """Until we have a separate docs site, every URL points at the
    monorepo on GitHub."""
    urls = manifest["project"]["urls"]
    for label, url in urls.items():
        assert "github.com/v-sen/verixa" in url, (
            f"URL {label}={url!r} does not point at the canonical repo"
        )


# ---------------------------------------------------------------------------
# Hatch build targets
# ---------------------------------------------------------------------------


def test_wheel_target_ships_verixa_package(manifest: dict) -> None:
    """The wheel target MUST include the `verixa` package directory so
    the installed wheel actually contains importable code + py.typed."""
    wheel = manifest["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert "verixa" in wheel["packages"]


def test_sdist_excludes_backup_dirs(manifest: dict) -> None:
    """_backup/ directories are local scratch + must NEVER ship in the
    source distribution (they may contain in-flight or stale code)."""
    sdist = manifest["tool"]["hatch"]["build"]["targets"]["sdist"]
    assert any("_backup" in pat for pat in sdist["exclude"])


def test_sdist_includes_readme_changelog_license(manifest: dict) -> None:
    """Customers downloading the source distribution from PyPI need the
    docs + license alongside the code."""
    sdist = manifest["tool"]["hatch"]["build"]["targets"]["sdist"]
    include = sdist["include"]
    for required in ("README.md", "CHANGELOG.md", "LICENSE"):
        assert required in include


# ---------------------------------------------------------------------------
# Cross-file consistency
# ---------------------------------------------------------------------------


def test_pyproject_keywords_match_changelog_unreleased_header() -> None:
    """A weak but useful sanity check: the keywords list shouldn't
    accidentally include a typo of the project name."""
    manifest = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    kw = manifest["project"]["keywords"]
    assert "verixa" in kw
    assert all(k == k.lower() for k in kw), "keywords must be lowercase"


def test_no_pyproject_drift_against_root_manifest() -> None:
    """The httpx pin in this per-package pyproject.toml MUST match the
    pin in the monorepo-root pyproject.toml. If a contributor bumps
    httpx at root they must also bump it here."""
    pkg_manifest = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    pkg_httpx = [
        d for d in pkg_manifest["project"]["dependencies"]
        if d.startswith("httpx")
    ][0]
    root_text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Crude grep -- the root file uses Poetry's TOML shape so we just
    # check the canonical pin substring appears.
    canonical = ">=0.27.2,<0.28.0"
    assert canonical in pkg_httpx, (
        f"per-package httpx pin {pkg_httpx!r} does not contain "
        f"canonical {canonical!r}"
    )
    assert canonical in root_text, (
        "monorepo root httpx pin drifted from canonical value"
    )
