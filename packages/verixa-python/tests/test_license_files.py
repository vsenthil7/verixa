"""CP-57 tests: LICENSE file presence in both SDK packages.

Both `pip install verixa` and `npm install @verixa/ts` ship LICENSE
inside the package tarball/wheel; the file MUST exist in the package
directory (not just at the monorepo root) for the published artifact
to include it. These tests pin the requirement so a future cleanup
cannot silently drop the LICENSE.

Both LICENSE files MUST match the canonical monorepo-root LICENSE
byte-for-byte; otherwise we end up with two slightly-different MIT
license texts which would be a legal mess.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROOT_LICENSE = _REPO_ROOT / "LICENSE"


def test_repo_root_license_exists() -> None:
    """Anchor: the canonical LICENSE lives at the monorepo root."""
    assert _ROOT_LICENSE.is_file()


def test_python_package_has_license_file() -> None:
    """packages/verixa-python/LICENSE MUST exist for the PyPI wheel
    to include it."""
    pkg_license = _REPO_ROOT / "packages" / "verixa-python" / "LICENSE"
    assert pkg_license.is_file(), (
        f"LICENSE missing at {pkg_license}; required for PyPI wheel."
    )


def test_ts_package_has_license_file() -> None:
    """packages/verixa-ts/LICENSE MUST exist for the npm tarball
    to include it (package.json's `files: [...]` lists LICENSE)."""
    pkg_license = _REPO_ROOT / "packages" / "verixa-ts" / "LICENSE"
    assert pkg_license.is_file(), (
        f"LICENSE missing at {pkg_license}; required for npm tarball."
    )


def test_python_package_license_matches_root() -> None:
    """The two LICENSE files MUST match byte-for-byte. If they diverge
    we have a legal ambiguity (which LICENSE applies?)."""
    root = _ROOT_LICENSE.read_bytes()
    pkg = (_REPO_ROOT / "packages" / "verixa-python" / "LICENSE").read_bytes()
    assert root == pkg, (
        "packages/verixa-python/LICENSE drifted from the monorepo root "
        "LICENSE. Re-copy from root to fix."
    )


def test_ts_package_license_matches_root() -> None:
    root = _ROOT_LICENSE.read_bytes()
    pkg = (_REPO_ROOT / "packages" / "verixa-ts" / "LICENSE").read_bytes()
    assert root == pkg, (
        "packages/verixa-ts/LICENSE drifted from the monorepo root "
        "LICENSE. Re-copy from root to fix."
    )


def test_license_is_mit() -> None:
    """Sanity: the LICENSE is the MIT license. Distribution + commercial
    use rights matter to enterprise customers."""
    content = _ROOT_LICENSE.read_text(encoding="utf-8")
    assert "MIT License" in content
    assert "Permission is hereby granted, free of charge" in content
