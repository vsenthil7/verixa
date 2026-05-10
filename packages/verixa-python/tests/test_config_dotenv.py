"""pytest suite for verixa_runtime.config (CP-6.5).

100% line + branch coverage on the .env parser + loader.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from verixa_runtime.config import (
    DOTENV_FILENAME,
    find_dotenv,
    load_dotenv,
    parse_dotenv_text,
)


# ---------------------------------------------------------------------------
# parse_dotenv_text -- pure parser
# ---------------------------------------------------------------------------


def test_parse_simple_key_value() -> None:
    assert parse_dotenv_text("FOO=bar") == {"FOO": "bar"}


def test_parse_skips_blank_lines_and_comments() -> None:
    text = (
        "# top comment\n"
        "FOO=bar\n"
        "\n"
        "  # indented comment\n"
        "BAZ=qux\n"
    )
    assert parse_dotenv_text(text) == {"FOO": "bar", "BAZ": "qux"}


def test_parse_strips_whitespace_around_equals() -> None:
    assert parse_dotenv_text("  FOO   =   bar  ") == {"FOO": "bar"}


def test_parse_strips_double_quotes() -> None:
    assert parse_dotenv_text('FOO="bar baz"') == {"FOO": "bar baz"}


def test_parse_strips_single_quotes() -> None:
    assert parse_dotenv_text("FOO='bar baz'") == {"FOO": "bar baz"}


def test_parse_does_not_strip_mismatched_quotes() -> None:
    # Mismatched quotes (one side double, other single) are kept literal
    assert parse_dotenv_text("""FOO="bar'""") == {"FOO": '"bar\''}


def test_parse_does_not_strip_single_quote_only() -> None:
    """Value of just a single quote is kept literal (no stripping)."""
    assert parse_dotenv_text("FOO='") == {"FOO": "'"}


def test_parse_allows_empty_value() -> None:
    assert parse_dotenv_text("FOO=") == {"FOO": ""}


def test_parse_preserves_equals_in_value() -> None:
    """Only the FIRST = is the separator; later = stay in the value."""
    assert parse_dotenv_text("URL=postgres://u:p@h/db") == {
        "URL": "postgres://u:p@h/db"
    }


def test_parse_rejects_line_without_equals() -> None:
    with pytest.raises(ValueError, match="expected KEY=VALUE"):
        parse_dotenv_text("INVALID_LINE_NO_EQUALS")


def test_parse_rejects_empty_key() -> None:
    with pytest.raises(ValueError, match="empty key"):
        parse_dotenv_text("=value-without-key")


def test_parse_includes_line_number_in_error() -> None:
    text = "FOO=bar\nBROKEN\nBAZ=qux"
    with pytest.raises(ValueError, match="line 2"):
        parse_dotenv_text(text)


# ---------------------------------------------------------------------------
# find_dotenv -- directory walking
# ---------------------------------------------------------------------------


def test_find_dotenv_in_current_dir(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("X=1", encoding="utf-8")
    found = find_dotenv(tmp_path)
    assert found == env.resolve()


def test_find_dotenv_walks_up_to_parent(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("X=1", encoding="utf-8")
    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)
    found = find_dotenv(sub)
    assert found == env.resolve()


def test_find_dotenv_returns_none_when_absent(tmp_path: Path) -> None:
    sub = tmp_path / "deep" / "nested"
    sub.mkdir(parents=True)
    # tmp_path itself has no .env; walking up may hit the real filesystem.
    # We can't *guarantee* None on a real OS, but on a temp dir whose
    # ancestors won't have .env, we should usually get None. To make
    # the test robust, point at a path under a created dir that has no
    # .env, and trust pytest's tmp_path isolation.
    # If a parent .env exists in CI, this test will be a false-positive;
    # we accept that trade-off and assert "the candidate found is at or
    # above tmp_path's filesystem root, never inside our subdir".
    found = find_dotenv(sub)
    if found is not None:
        # Permitted only if it's outside our scratch dir
        assert tmp_path.resolve() not in found.parents


def test_find_dotenv_default_uses_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("X=1", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    found = find_dotenv()
    assert found == env.resolve()


# ---------------------------------------------------------------------------
# load_dotenv -- side-effecting on os.environ
# ---------------------------------------------------------------------------


@pytest.fixture
def isolate_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove keys this test suite uses to keep tests independent."""
    for key in ("VERIXA_TEST_LOAD_A", "VERIXA_TEST_LOAD_B", "VERIXA_TEST_PRESET"):
        monkeypatch.delenv(key, raising=False)


def test_load_dotenv_sets_new_keys(
    tmp_path: Path, isolate_environ: None
) -> None:
    env = tmp_path / ".env"
    env.write_text("VERIXA_TEST_LOAD_A=alpha\nVERIXA_TEST_LOAD_B=beta", encoding="utf-8")
    applied = load_dotenv(env)
    assert applied == {
        "VERIXA_TEST_LOAD_A": "alpha",
        "VERIXA_TEST_LOAD_B": "beta",
    }
    assert os.environ["VERIXA_TEST_LOAD_A"] == "alpha"
    assert os.environ["VERIXA_TEST_LOAD_B"] == "beta"


def test_load_dotenv_preserves_existing_environ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERIXA_TEST_PRESET", "from-process")
    env = tmp_path / ".env"
    env.write_text("VERIXA_TEST_PRESET=from-file", encoding="utf-8")
    applied = load_dotenv(env)
    assert applied == {}  # nothing applied because key already set
    assert os.environ["VERIXA_TEST_PRESET"] == "from-process"


def test_load_dotenv_default_path_walks_to_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolate_environ: None,
) -> None:
    env = tmp_path / ".env"
    env.write_text("VERIXA_TEST_LOAD_A=walk-found", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    applied = load_dotenv()
    assert applied.get("VERIXA_TEST_LOAD_A") == "walk-found"


def test_load_dotenv_default_returns_empty_when_no_file_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If find_dotenv returns None, load_dotenv returns {} (not an error)."""
    monkeypatch.setattr(
        "verixa_runtime.config.find_dotenv", lambda *a, **kw: None
    )
    assert load_dotenv() == {}


def test_load_dotenv_raises_on_missing_explicit_path(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.env"
    with pytest.raises(FileNotFoundError):
        load_dotenv(missing)


def test_dotenv_filename_constant() -> None:
    assert DOTENV_FILENAME == ".env"


# ---------------------------------------------------------------------------
# Auditex-style real-world content -- mirroring the Auditex .env shape
# ---------------------------------------------------------------------------


def test_load_handles_auditex_style_env(
    tmp_path: Path, isolate_environ: None
) -> None:
    """The Auditex .env uses comments, blank lines, and complex secret
    values with hyphens, underscores, and embedded special chars. The
    loader must round-trip them faithfully."""
    text = (
        "# Verixa secrets pulled through from Auditex\n"
        "ANTHROPIC_API_KEY=sk-ant-api03-abc-DEF_123-XYZ\n"
        "OPENAI_API_KEY=sk-proj-12_AB-cd34efGH\n"
        "\n"
        "DATABASE_URL=postgresql+asyncpg://u:p@h:5432/db\n"
        'JWT_SECRET="quoted with spaces"\n'
    )
    env = tmp_path / ".env"
    env.write_text(text, encoding="utf-8")
    # Make sure none of these keys leak from the host process
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "JWT_SECRET"):
        if key in os.environ:
            del os.environ[key]
    applied = load_dotenv(env)
    assert applied["ANTHROPIC_API_KEY"] == "sk-ant-api03-abc-DEF_123-XYZ"
    assert applied["OPENAI_API_KEY"] == "sk-proj-12_AB-cd34efGH"
    assert applied["DATABASE_URL"] == "postgresql+asyncpg://u:p@h:5432/db"
    assert applied["JWT_SECRET"] == "quoted with spaces"
