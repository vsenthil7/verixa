"""Policy bundle loader -- structural validation of policies/ directory.

A "bundle" in OPA terms is a tarball containing:
  - .manifest    JSON manifest declaring revision + roots
  - one or more .rego files implementing the package(s)

In Verixa's source tree these live unpacked under ``policies/<pack>/``.
The loader walks the directory and produces typed records the runtime
can use to validate the layout, sign bundles (CP-8.4), and feed test
fixtures into CI (CP-8.1).

No OPA invocation here -- live policy evaluation goes through
``verixa_runtime.policy.client`` (CP-8.3).

Public API:
  - ``PolicyBundle``       frozen dataclass for one pack
  - ``PolicyEntry``        frozen dataclass for one .rego
  - ``PolicyFixture``      frozen dataclass for a single test case
  - ``PolicyBundleError``  raised on malformed bundles
  - ``load_bundle(path)``  parse one pack directory
  - ``discover_bundles(root)``  walk the policies/ tree
  - ``load_fixtures(path)`` parse a fixtures JSON file
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PolicyBundleError(ValueError):
    """Raised when a bundle directory has malformed structure."""


class PolicyTestExpected(str, Enum):
    """Expected outcome of a policy fixture (matches docs/06_data_model A7 4.2)."""

    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"


@dataclass(frozen=True, slots=True)
class PolicyEntry:
    """A single .rego file within a bundle."""

    name: str  # e.g. "pii_redaction"
    package: str  # e.g. "verixa.core.pii_redaction"
    source_path: Path
    source_text: str


@dataclass(frozen=True, slots=True)
class PolicyFixture:
    """A single test case for a policy."""

    name: str
    expected_result: PolicyTestExpected
    expected_reason: str
    input: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PolicyBundle:
    """A loaded ``policies/<pack>/`` directory."""

    name: str  # e.g. "core"
    revision: str
    roots: tuple[str, ...]
    metadata: dict[str, Any]
    policies: tuple[PolicyEntry, ...] = field(default_factory=tuple)


def _read_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise PolicyBundleError(
            f"missing .manifest in bundle: {manifest_path.parent}"
        )
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PolicyBundleError(
            f"invalid JSON in {manifest_path}: {e}"
        ) from e
    if not isinstance(data, dict):
        raise PolicyBundleError(
            f"manifest must be a JSON object: {manifest_path}"
        )
    for required in ("revision", "roots"):
        if required not in data:
            raise PolicyBundleError(
                f"manifest missing required key {required!r}: {manifest_path}"
            )
    if not isinstance(data["roots"], list):
        raise PolicyBundleError(
            f"manifest 'roots' must be a list: {manifest_path}"
        )
    return data


def _extract_package(rego_text: str, source_path: Path) -> str:
    """Pull the ``package`` declaration out of a .rego file.

    Tolerated forms:
      - ``package verixa.x``   (whitespace after package required, name follows)
      - ``package    verixa.x`` (multiple spaces ok)
      - ``package\\tverixa.x`` (tab after keyword)

    Rejected forms:
      - ``package`` alone (bare keyword, no name)
      - ``import ...`` before ``package`` (not a package declaration)
      - file with only comments / blank lines (no package)
    """
    for raw in rego_text.splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        # The keyword must be either "package" alone or "package <name>".
        if line == "package":
            raise PolicyBundleError(
                f"empty package declaration in {source_path}"
            )
        if line.startswith("package ") or line.startswith("package\t"):
            # `startswith("package ")` guarantees at least one whitespace
            # after the keyword; the strip below produces a non-empty name
            # because the line itself is not equal to "package" (handled
            # above) -- there's at least one non-whitespace character.
            return line[len("package") :].strip()
        # Hit a non-package non-comment line first -- malformed
        raise PolicyBundleError(
            f"first non-comment line in {source_path} is not a package "
            f"declaration; got {line!r}"
        )
    raise PolicyBundleError(
        f"no package declaration found in {source_path}"
    )


def load_bundle(bundle_dir: Path) -> PolicyBundle:
    """Parse a single ``policies/<pack>/`` directory into a ``PolicyBundle``."""
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir():
        raise PolicyBundleError(f"not a directory: {bundle_dir}")

    manifest = _read_manifest(bundle_dir / ".manifest")

    entries: list[PolicyEntry] = []
    for rego_path in sorted(bundle_dir.glob("*.rego")):
        text = rego_path.read_text(encoding="utf-8")
        package = _extract_package(text, rego_path)
        entries.append(
            PolicyEntry(
                name=rego_path.stem,
                package=package,
                source_path=rego_path.resolve(),
                source_text=text,
            )
        )

    if not entries:
        raise PolicyBundleError(
            f"bundle has no .rego policies: {bundle_dir}"
        )

    return PolicyBundle(
        name=bundle_dir.name,
        revision=str(manifest["revision"]),
        roots=tuple(manifest["roots"]),
        metadata=dict(manifest.get("metadata", {})),
        policies=tuple(entries),
    )


def discover_bundles(policies_root: Path) -> list[PolicyBundle]:
    """Walk ``policies_root`` returning a sorted list of bundles.

    Each immediate subdirectory containing a ``.manifest`` is a bundle.
    Directories without a manifest are skipped silently (allows
    documentation / tooling subdirs to coexist).
    """
    policies_root = Path(policies_root)
    if not policies_root.is_dir():
        raise PolicyBundleError(f"not a directory: {policies_root}")
    out: list[PolicyBundle] = []
    for child in sorted(policies_root.iterdir()):
        if not child.is_dir():
            continue
        if not (child / ".manifest").is_file():
            continue
        out.append(load_bundle(child))
    return out


def load_fixtures(fixtures_path: Path) -> list[PolicyFixture]:
    """Load a fixtures JSON file into a list of ``PolicyFixture``."""
    fixtures_path = Path(fixtures_path)
    if not fixtures_path.is_file():
        raise PolicyBundleError(
            f"fixtures file not found: {fixtures_path}"
        )
    raw = json.loads(fixtures_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise PolicyBundleError(
            f"fixtures root must be a JSON object: {fixtures_path}"
        )
    items = raw.get("fixtures")
    if not isinstance(items, list):
        raise PolicyBundleError(
            f"fixtures.fixtures must be a list: {fixtures_path}"
        )
    out: list[PolicyFixture] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise PolicyBundleError(
                f"fixture {index} is not an object in {fixtures_path}"
            )
        for required in ("name", "expected_result", "input"):
            if required not in item:
                raise PolicyBundleError(
                    f"fixture {index} missing {required!r} in {fixtures_path}"
                )
        try:
            expected = PolicyTestExpected(item["expected_result"])
        except ValueError as e:
            raise PolicyBundleError(
                f"fixture {index} has invalid expected_result "
                f"{item['expected_result']!r} in {fixtures_path}"
            ) from e
        out.append(
            PolicyFixture(
                name=str(item["name"]),
                expected_result=expected,
                expected_reason=str(item.get("expected_reason", "")),
                input=dict(item["input"]),
            )
        )
    return out
