"""CP-54 -- OpenAPI schema export + drift-detection CLI.

Closes the Phase-1 carry-forward "checked-in OpenAPI schema for SDK
generation pipelines + drift detection" item. The control-plane FastAPI
generates a live ``/openapi.json`` at runtime, but customer SDK generation
pipelines (OpenAPI Generator, Speakeasy, Stainless) need a CHECKED-IN
frozen schema artifact for:

  - Version control + diff review on every route change
  - Reproducible SDK builds (the live endpoint depends on app state)
  - Drift detection in CI (if the live spec drifts from the committed
    one without a deliberate update, CI fails)
  - Customer-facing docs site can serve a stable URL

The committed artifact lives at ``docs/openapi.json`` and is regenerated
via this CLI on every route change. CI runs ``openapi_export diff`` to
fail the build if the committed file is stale.

Subcommands:

    python -m tools.openapi_export generate
        Write the current FastAPI schema to docs/openapi.json. Overwrites
        existing file. Pretty-printed JSON with sorted keys for clean diffs.

    python -m tools.openapi_export diff
        Compare the live schema against docs/openapi.json. Exit 0 if they
        match, exit 2 if drift detected (CI uses this to gate merges).

    python -m tools.openapi_export show
        Print metadata: openapi version + path count + sorted path list.
        Useful for quick verification without diffing the full JSON.

The schema is normalised before write + compare:
  - JSON keys sorted at every level
  - 2-space indent
  - Trailing newline on file write
  - UTF-8 encoding

These normalisations are critical: a non-deterministic dict-order or
indent-width change would produce false drift on every regeneration.

Exit codes:
  0  -- success / no drift
  1  -- invalid arguments or runtime error
  2  -- drift detected (CI uses this to gate merges)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from verixa_control_plane.routes import create_app_with_state

# Canonical path for the committed schema artifact. Relative to repo root.
_DEFAULT_ARTIFACT = "docs/openapi.json"


def _generate_live_schema() -> dict[str, Any]:
    """Build the FastAPI app + return its current OpenAPI schema dict.

    Uses build_default_state which produces a Phase-0 in-memory state.
    The schema is deterministic across runs because FastAPI's openapi()
    method does not depend on app state (only on registered routes +
    Pydantic models).
    """
    app = create_app_with_state()
    return app.openapi()


def _normalise(spec: dict[str, Any]) -> str:
    """Canonicalise a schema dict into a stable JSON string.

    Sorts keys at every level + 2-space indent + trailing newline.
    Without sort_keys=True the JSON would be order-dependent and any
    Python dict-order change (or hash-randomisation across runs) would
    produce false drift.
    """
    return json.dumps(spec, sort_keys=True, indent=2) + "\n"


def _read_committed(path: Path) -> str:
    """Read a committed schema file as a canonical string for diff."""
    if not path.is_file():
        raise FileNotFoundError(
            f"committed schema not found at {path}; "
            f"run `python -m tools.openapi_export generate` first"
        )
    return path.read_text(encoding="utf-8")


def _cmd_generate(args: argparse.Namespace) -> int:
    """Write the live schema to the artifact path."""
    out_path = Path(args.out)
    spec = _generate_live_schema()
    canon = _normalise(spec)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(canon, encoding="utf-8")
    print(
        f"Wrote {len(canon):,} bytes to {out_path}\n"
        f"  openapi: {spec['openapi']}\n"
        f"  paths:   {len(spec['paths'])}\n"
        f"  title:   {spec['info']['title']}\n"
        f"  version: {spec['info']['version']}"
    )
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    """Compare the live schema against the committed file.

    Exit 0 if they match (no drift), exit 2 if they differ. CI uses
    exit-2 to gate merges so that any route change forces an explicit
    `generate` step before merge.
    """
    artifact_path = Path(args.artifact)
    try:
        committed = _read_committed(artifact_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    live = _normalise(_generate_live_schema())
    if committed == live:
        print(f"OK: {artifact_path} matches the live schema")
        return 0
    # Find a few specific differences to display
    committed_spec = json.loads(committed)
    live_spec = json.loads(live)
    committed_paths = set(committed_spec.get("paths", {}).keys())
    live_paths = set(live_spec.get("paths", {}).keys())
    added = live_paths - committed_paths
    removed = committed_paths - live_paths
    print(
        f"DRIFT DETECTED: live schema differs from {artifact_path}",
        file=sys.stderr,
    )
    if added:
        print(
            f"  routes added:   {sorted(added)}",
            file=sys.stderr,
        )
    if removed:
        print(
            f"  routes removed: {sorted(removed)}",
            file=sys.stderr,
        )
    if not added and not removed:
        print(
            "  (no path-set changes; schema-body changed -- run "
            "`generate` and review the JSON diff)",
            file=sys.stderr,
        )
    print(
        f"Run `python -m tools.openapi_export generate "
        f"--out {artifact_path}` and commit the result.",
        file=sys.stderr,
    )
    return 2


def _cmd_show(args: argparse.Namespace) -> int:
    """Print high-level metadata about the live schema."""
    spec = _generate_live_schema()
    paths = sorted(spec.get("paths", {}).keys())
    print(f"openapi: {spec['openapi']}")
    print(f"title:   {spec['info']['title']}")
    print(f"version: {spec['info']['version']}")
    print(f"paths:   {len(paths)}")
    if args.verbose:
        for p in paths:
            ops = sorted(spec["paths"][p].keys())
            print(f"  {p}  [{','.join(ops)}]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openapi_export",
        description=(
            "OpenAPI schema export + drift-detection CLI. Generates the "
            "canonical docs/openapi.json artifact used by SDK generation "
            "pipelines + CI drift gates."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser(
        "generate", help="write the live schema to disk (overwrites)"
    )
    p_gen.add_argument(
        "--out",
        default=_DEFAULT_ARTIFACT,
        help=f"path for committed schema (default: {_DEFAULT_ARTIFACT})",
    )
    p_gen.set_defaults(func=_cmd_generate)

    p_diff = sub.add_parser(
        "diff",
        help=(
            "compare live schema vs committed file; exit 2 on drift "
            "(CI gate)"
        ),
    )
    p_diff.add_argument(
        "--artifact",
        default=_DEFAULT_ARTIFACT,
        help=f"path to committed schema (default: {_DEFAULT_ARTIFACT})",
    )
    p_diff.set_defaults(func=_cmd_diff)

    p_show = sub.add_parser(
        "show", help="print live schema metadata"
    )
    p_show.add_argument(
        "--verbose",
        action="store_true",
        help="also list every path with its HTTP methods",
    )
    p_show.set_defaults(func=_cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
