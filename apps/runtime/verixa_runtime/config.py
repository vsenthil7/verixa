"""Verixa configuration loader -- reads .env files into os.environ.

Auditex-compatible: same .env format, same var-naming conventions. A
single dev .env can back both repositories.

Why a custom loader rather than python-dotenv? Two reasons:
  1. Zero new dependencies; this is ~30 lines of pure stdlib.
  2. We control the precedence rule: existing process-environ wins over
     .env file (so Docker / CI overrides survive).

Usage:
    from verixa_runtime.config import load_dotenv

    load_dotenv()                      # default: walks up to first .env
    load_dotenv(Path("./local.env"))   # explicit path

The loader is idempotent: calling it twice with the same file returns
without changing already-set variables. Exposed for tests to clear and
re-load.

Public API:
  - `load_dotenv(path=None)`           -> dict[str, str] of keys loaded
  - `parse_dotenv_text(text)`          -> dict[str, str] (pure parser)
  - `find_dotenv(start_dir=None)`      -> Path | None
"""

from __future__ import annotations

import os
from pathlib import Path

DOTENV_FILENAME = ".env"


def parse_dotenv_text(text: str) -> dict[str, str]:
    """Parse the contents of a .env file.

    Supported syntax:
      - KEY=VALUE
      - blank lines (skipped)
      - lines starting with `#` (skipped as comments)
      - leading/trailing whitespace on each side of `=` is stripped
      - surrounding double or single quotes on VALUE are stripped
      - lines with no `=` raise ValueError

    Empty values (KEY=) are allowed and produce an empty string.
    """
    out: dict[str, str] = {}
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"line {line_no}: expected KEY=VALUE, got {raw!r}"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"line {line_no}: empty key in {raw!r}")
        # Strip matching surrounding quotes (single or double, both ends)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        out[key] = value
    return out


def find_dotenv(start_dir: Path | None = None) -> Path | None:
    """Walk up from `start_dir` (default: cwd) looking for a `.env`.

    Returns the first match or ``None`` if no .env is found before the
    filesystem root.
    """
    here = Path(start_dir) if start_dir is not None else Path.cwd()
    here = here.resolve()
    for candidate in [here, *here.parents]:
        env_path = candidate / DOTENV_FILENAME
        if env_path.is_file():
            return env_path
    return None


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """Load a .env file into ``os.environ``.

    Precedence: existing ``os.environ`` values are NOT overwritten. This
    matches docker-compose / CI semantics where the runtime environment
    has authority over the file.

    Returns the dict of (key, value) pairs that were ACTUALLY applied
    (i.e. excludes keys already present in os.environ).

    If `path` is None, walks up from cwd to find the first .env. If no
    .env is found, returns an empty dict (not an error).
    """
    if path is None:
        found = find_dotenv()
        if found is None:
            return {}
        path = found
    if not path.is_file():
        raise FileNotFoundError(f"no such .env file: {path}")
    parsed = parse_dotenv_text(path.read_text(encoding="utf-8"))
    applied: dict[str, str] = {}
    for key, value in parsed.items():
        if key in os.environ:
            continue
        os.environ[key] = value
        applied[key] = value
    return applied
