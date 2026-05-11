"""Build the Hugging Face Space repo directory (CP-17).

HF Spaces expects the Dockerfile + README.md at the *repo root* of
the Space, with sources directly accessible. This script assembles
the right tree under a destination directory by copying:

  - deploy/huggingface/Dockerfile        -> {dest}/Dockerfile
  - deploy/huggingface/README.md         -> {dest}/README.md
  - deploy/huggingface/.dockerignore     -> {dest}/.dockerignore
  - apps/runtime/verixa_runtime          -> {dest}/apps/runtime/verixa_runtime
  - apps/control-plane-api/verixa_control_plane
                                         -> {dest}/apps/control-plane-api/verixa_control_plane
  - packages/verixa-python/verixa        -> {dest}/packages/verixa-python/verixa

Then the user `cd {dest}` and `git push` to the Space's git remote.

Usage:
    python deploy/huggingface/build_space_repo.py --dest ./hf_space_build

The destination is wiped on each run so the resulting repo is
reproducible. We do NOT auto-push -- that requires HF credentials
and would surprise a user running this locally.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEPLOY_DIR = REPO_ROOT / "deploy" / "huggingface"


# (source, relative-destination) pairs.
ASSETS: list[tuple[Path, str]] = [
    (DEPLOY_DIR / "Dockerfile", "Dockerfile"),
    (DEPLOY_DIR / "README.md", "README.md"),
    (DEPLOY_DIR / ".dockerignore", ".dockerignore"),
]

PACKAGES: list[tuple[Path, str]] = [
    (
        REPO_ROOT / "apps" / "runtime" / "verixa_runtime",
        "apps/runtime/verixa_runtime",
    ),
    (
        REPO_ROOT / "apps" / "control-plane-api" / "verixa_control_plane",
        "apps/control-plane-api/verixa_control_plane",
    ),
    (
        REPO_ROOT / "packages" / "verixa-python" / "verixa",
        "packages/verixa-python/verixa",
    ),
]


def _ignore_caches(_dir: str, names: list[str]) -> list[str]:
    """shutil.copytree filter -- skip caches + bytecode."""
    return [
        n for n in names
        if n in ("__pycache__", ".pytest_cache", ".mypy_cache",
                 ".ruff_cache", "htmlcov")
        or n.endswith(".pyc")
    ]


def build(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    print(f"Building HF Space repo at {dest}")
    for src, rel in ASSETS:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        print(f"  copied {src.relative_to(REPO_ROOT)} -> {rel}")

    for src, rel in PACKAGES:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, target, ignore=_ignore_caches)
        print(f"  copied {src.relative_to(REPO_ROOT)} -> {rel}")

    print()
    print("Done. To deploy:")
    print(f"  cd {dest}")
    print("  git init && git remote add origin "
          "https://huggingface.co/spaces/<your-user>/<space-name>")
    print("  git add . && git commit -m 'initial commit'")
    print("  git push -u origin main")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        type=Path,
        default=REPO_ROOT / "hf_space_build",
        help=(
            "Destination directory for the assembled HF Space "
            "repo (will be wiped + recreated). "
            "Default: ./hf_space_build at the verixa repo root."
        ),
    )
    args = parser.parse_args(argv)
    build(args.dest.resolve())
    return 0


if __name__ == "__main__":  # pragma: no cover -- CLI entry-point
    sys.exit(main())
