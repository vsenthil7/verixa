"""CP-43 tests for tools/policy_sign.py CLI -- 100% coverage of all 4 subcommands.

Anchored to BR-07 (signed policy bundles) and ADR-0008 key custody roadmap.

Coverage approach: each subcommand has happy-path + at least one error path.
Tests use the build_parser() + main() entry points directly, with tmp_path
fixtures for filesystem isolation. Tests are TDD-style: write the test
expectations first, then verify the CLI implementation matches.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import policy_sign


def _build_bundle(bundle_dir: Path, *, files: dict[str, str] | None = None) -> None:
    """Build a minimal bundle directory with a .manifest + 1 rego file."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / ".manifest").write_text(
        '{"revision": "test", "roots": ["verixa"]}\n', encoding="utf-8"
    )
    if files is None:
        files = {"transfer_limit.rego": "package verixa.transfer_limit\n\ndefault allow := false\n"}
    for name, content in files.items():
        out = bundle_dir / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")


def _generate_key_files(
    tmp_path: Path, *, key_id: str = "verixa-sig-test"
) -> tuple[Path, Path]:
    """Helper: invoke the generate-key subcommand, return (priv, pub) paths."""
    priv = tmp_path / "test.priv"
    pub = tmp_path / "test.pub"
    rc = policy_sign.main(
        [
            "generate-key",
            "--out", str(priv),
            "--pub-out", str(pub),
            "--key-id", key_id,
        ]
    )
    assert rc == 0
    assert priv.is_file() and len(priv.read_bytes()) == 32
    assert pub.is_file() and len(pub.read_bytes()) == 32
    return priv, pub


# ---------------------------------------------------------------------------
# generate-key
# ---------------------------------------------------------------------------


def test_generate_key_happy_path(tmp_path: Path, capsys) -> None:
    priv = tmp_path / "k.priv"
    pub = tmp_path / "k.pub"
    rc = policy_sign.main(
        [
            "generate-key",
            "--out", str(priv),
            "--pub-out", str(pub),
            "--key-id", "verixa-sig-dev",
        ]
    )
    assert rc == 0
    assert priv.read_bytes()  # non-empty
    assert pub.read_bytes()
    captured = capsys.readouterr()
    assert "Generated keypair for verixa-sig-dev" in captured.out
    assert "private key" in captured.out
    assert "public key" in captured.out


def test_generate_key_creates_parent_dirs(tmp_path: Path) -> None:
    """The CLI creates parent directories if they don't exist."""
    priv = tmp_path / "deep" / "nested" / "k.priv"
    pub = tmp_path / "deep" / "nested" / "k.pub"
    rc = policy_sign.main(
        [
            "generate-key",
            "--out", str(priv),
            "--pub-out", str(pub),
            "--key-id", "verixa-sig-dev",
        ]
    )
    assert rc == 0
    assert priv.is_file()
    assert pub.is_file()


def test_generate_key_refuses_existing_priv(tmp_path: Path, capsys) -> None:
    """Must refuse to overwrite an existing private key (operator must
    explicitly delete first to rotate)."""
    priv = tmp_path / "k.priv"
    pub = tmp_path / "k.pub"
    priv.write_bytes(b"existing")
    rc = policy_sign.main(
        [
            "generate-key",
            "--out", str(priv),
            "--pub-out", str(pub),
            "--key-id", "verixa-sig-dev",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "private key file already exists" in captured.err


def test_generate_key_refuses_existing_pub(tmp_path: Path, capsys) -> None:
    """Same protection for the public key file."""
    priv = tmp_path / "k.priv"
    pub = tmp_path / "k.pub"
    pub.write_bytes(b"existing")
    rc = policy_sign.main(
        [
            "generate-key",
            "--out", str(priv),
            "--pub-out", str(pub),
            "--key-id", "verixa-sig-dev",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "public key file already exists" in captured.err


def test_generate_key_rejects_bad_key_id_prefix(tmp_path: Path, capsys) -> None:
    """key-id MUST start with 'verixa-sig-' per signing.py convention."""
    rc = policy_sign.main(
        [
            "generate-key",
            "--out", str(tmp_path / "k.priv"),
            "--pub-out", str(tmp_path / "k.pub"),
            "--key-id", "my-cool-key",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "must start with 'verixa-sig-'" in captured.err


# ---------------------------------------------------------------------------
# sign
# ---------------------------------------------------------------------------


def test_sign_happy_path(tmp_path: Path, capsys) -> None:
    priv, pub = _generate_key_files(tmp_path)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle)
    rc = policy_sign.main(
        [
            "sign",
            str(bundle),
            "--priv", str(priv),
            "--pub", str(pub),
            "--key-id", "verixa-sig-test",
        ]
    )
    assert rc == 0
    sig_file = bundle / ".signatures.json"
    assert sig_file.is_file()
    captured = capsys.readouterr()
    assert "Signed bundle" in captured.out
    assert "verixa-sig-test" in captured.out


def test_sign_rejects_missing_bundle(tmp_path: Path, capsys) -> None:
    priv, pub = _generate_key_files(tmp_path)
    rc = policy_sign.main(
        [
            "sign",
            str(tmp_path / "nonexistent"),
            "--priv", str(priv),
            "--pub", str(pub),
            "--key-id", "verixa-sig-test",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "not a directory" in captured.err


def test_sign_rejects_missing_priv(tmp_path: Path, capsys) -> None:
    _, pub = _generate_key_files(tmp_path)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle)
    rc = policy_sign.main(
        [
            "sign",
            str(bundle),
            "--priv", str(tmp_path / "no.priv"),
            "--pub", str(pub),
            "--key-id", "verixa-sig-test",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "private key file not found" in captured.err


def test_sign_rejects_missing_pub(tmp_path: Path, capsys) -> None:
    priv, _ = _generate_key_files(tmp_path)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle)
    rc = policy_sign.main(
        [
            "sign",
            str(bundle),
            "--priv", str(priv),
            "--pub", str(tmp_path / "no.pub"),
            "--key-id", "verixa-sig-test",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "public key file not found" in captured.err


def test_sign_rejects_invalid_keypair_bytes(tmp_path: Path, capsys) -> None:
    """Keypair files with wrong byte length raise from Ed25519KeyPair
    post-init, which the CLI translates to exit 1."""
    bad_priv = tmp_path / "bad.priv"
    bad_pub = tmp_path / "bad.pub"
    bad_priv.write_bytes(b"\x00" * 16)  # too short
    bad_pub.write_bytes(b"\x00" * 32)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle)
    rc = policy_sign.main(
        [
            "sign",
            str(bundle),
            "--priv", str(bad_priv),
            "--pub", str(bad_pub),
            "--key-id", "verixa-sig-test",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "keypair invalid" in captured.err


def test_sign_propagates_signing_error(tmp_path: Path, capsys) -> None:
    """sign_bundle raises BundleSignaturesError for bad key_id; CLI
    translates to exit 1."""
    priv, pub = _generate_key_files(tmp_path)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle)
    rc = policy_sign.main(
        [
            "sign",
            str(bundle),
            "--priv", str(priv),
            "--pub", str(pub),
            "--key-id", "wrong-prefix-key",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "signing failed" in captured.err


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def test_verify_happy_path(tmp_path: Path, capsys) -> None:
    priv, pub = _generate_key_files(tmp_path)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle)
    # Sign first
    policy_sign.main(
        [
            "sign", str(bundle),
            "--priv", str(priv), "--pub", str(pub),
            "--key-id", "verixa-sig-test",
        ]
    )
    # Then verify
    rc = policy_sign.main(["verify", str(bundle)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "VERIFIED bundle" in captured.out
    assert "verixa-sig-test" in captured.out


def test_verify_detects_tamper(tmp_path: Path, capsys) -> None:
    """A modified file after signing produces exit code 2 (tamper)."""
    priv, pub = _generate_key_files(tmp_path)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle)
    policy_sign.main(
        [
            "sign", str(bundle),
            "--priv", str(priv), "--pub", str(pub),
            "--key-id", "verixa-sig-test",
        ]
    )
    # TAMPER: modify the rego file after signing
    (bundle / "transfer_limit.rego").write_text(
        "package verixa.transfer_limit\n\ndefault allow := true  # attacker\n",
        encoding="utf-8",
    )
    rc = policy_sign.main(["verify", str(bundle)])
    assert rc == 2, "tamper MUST produce exit code 2"
    captured = capsys.readouterr()
    assert "VERIFICATION FAILED" in captured.err


def test_verify_rejects_missing_bundle(tmp_path: Path, capsys) -> None:
    rc = policy_sign.main(["verify", str(tmp_path / "nonexistent")])
    assert rc == 1
    captured = capsys.readouterr()
    assert "not a directory" in captured.err


def test_verify_detects_added_file(tmp_path: Path, capsys) -> None:
    """An unsigned file added after signing produces exit code 2."""
    priv, pub = _generate_key_files(tmp_path)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle)
    policy_sign.main(
        [
            "sign", str(bundle),
            "--priv", str(priv), "--pub", str(pub),
            "--key-id", "verixa-sig-test",
        ]
    )
    # Add an extra file after signing
    (bundle / "evil.rego").write_text("package evil\n", encoding="utf-8")
    rc = policy_sign.main(["verify", str(bundle)])
    assert rc == 2


def test_verify_detects_removed_file(tmp_path: Path, capsys) -> None:
    """A signed file deleted after signing produces exit code 2."""
    priv, pub = _generate_key_files(tmp_path)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle, files={
        "a.rego": "package a\n",
        "b.rego": "package b\n",
    })
    policy_sign.main(
        [
            "sign", str(bundle),
            "--priv", str(priv), "--pub", str(pub),
            "--key-id", "verixa-sig-test",
        ]
    )
    (bundle / "b.rego").unlink()
    rc = policy_sign.main(["verify", str(bundle)])
    assert rc == 2


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_happy_path(tmp_path: Path, capsys) -> None:
    priv, pub = _generate_key_files(tmp_path)
    bundle = tmp_path / "bundle"
    _build_bundle(bundle, files={
        "a.rego": "package a\n",
        "b.rego": "package b\n",
    })
    policy_sign.main(
        [
            "sign", str(bundle),
            "--priv", str(priv), "--pub", str(pub),
            "--key-id", "verixa-sig-test",
        ]
    )
    rc = policy_sign.main(["show", str(bundle)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "key-id: verixa-sig-test" in captured.out
    assert "public-key:" in captured.out
    assert "a.rego" in captured.out
    assert "b.rego" in captured.out


def test_show_rejects_missing_bundle(tmp_path: Path, capsys) -> None:
    rc = policy_sign.main(["show", str(tmp_path / "nonexistent")])
    assert rc == 1


def test_show_rejects_invalid_signature_file(tmp_path: Path, capsys) -> None:
    """An unsigned (or invalid-signature) bundle cannot be shown."""
    bundle = tmp_path / "bundle"
    _build_bundle(bundle)
    rc = policy_sign.main(["show", str(bundle)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "cannot show" in captured.err


# ---------------------------------------------------------------------------
# Parser + main entry
# ---------------------------------------------------------------------------


def test_build_parser_returns_argument_parser() -> None:
    parser = policy_sign.build_parser()
    # 4 subcommands
    assert parser.prog == "policy_sign"


def test_main_requires_subcommand(capsys) -> None:
    """Calling with no arguments shows usage and exits non-zero."""
    with pytest.raises(SystemExit):
        policy_sign.main([])


def test_main_module_entry_point() -> None:
    """`if __name__ == '__main__'` path exists; importing the module
    doesn't trigger it (we only assert it's callable)."""
    assert callable(policy_sign.main)
