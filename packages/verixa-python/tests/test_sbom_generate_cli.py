"""CP-44 tests for tools/sbom_generate.py CycloneDX SBOM wrapper.

Anchored to Phase-1 supply-chain artifact gap from BUILD_PLAN.md
section 3.2 + Phase-2 CycloneDX SBOM commitment. Tests cover:

  - cyclonedx-bom subprocess invocation (mocked to avoid slow real runs)
  - SBOM JSON structural validation (positive + 8 negative shapes)
  - Component summary flattening + PEP 503 normalisation
  - Ed25519 signing + signature sidecar shape (positive + 5 negatives)
  - All 4 subcommands (generate, sign, verify, show) happy + error paths
  - Verify-with-signature 3-way exit code semantics (0 / 2 / 3)

Subprocess mocking strategy: tests that exercise cyclonedx-bom invocation
patch `subprocess.run` to return a synthesised CompletedProcess and write
a canned SBOM JSON to the expected output path. This keeps tests fast and
deterministic without losing coverage of the wrapper logic.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from verixa_runtime.crypto.ed25519 import generate_keypair

from tools import sbom_generate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_MINIMAL_SBOM: dict[str, Any] = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "serialNumber": "urn:uuid:11111111-2222-3333-4444-555555555555",
    "version": 1,
    "metadata": {
        "timestamp": "2026-05-11T15:00:00+00:00",
        "tools": {
            "components": [
                {"name": "cyclonedx-py", "version": "7.3.0"}
            ]
        },
    },
    "components": [
        {
            "type": "library", "name": "fastapi", "version": "0.115.14",
            "purl": "pkg:pypi/fastapi@0.115.14",
            "bom-ref": "pkg:pypi/fastapi@0.115.14",
        },
        {
            "type": "library", "name": "pydantic", "version": "2.11.10",
            "purl": "pkg:pypi/pydantic@2.11.10",
            "bom-ref": "pkg:pypi/pydantic@2.11.10",
        },
    ],
}


def _write_minimal_sbom(path: Path, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write a deep-copied minimal SBOM to path, optionally with overrides."""
    body = json.loads(json.dumps(_MINIMAL_SBOM))
    if overrides:
        body.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")
    return body


def _fake_cyclonedx_run(
    *,
    sbom: dict[str, Any] | None = None,
    exit_code: int = 0,
    stderr: str = "",
):
    """Build a subprocess.run replacement that writes `sbom` to the -o path."""
    body = sbom if sbom is not None else _MINIMAL_SBOM

    def _runner(cmd, capture_output=True, text=True, check=False, **kw):  # noqa: ARG001
        # Find the -o argument in the command list
        if exit_code == 0:
            out_idx = cmd.index("-o") + 1
            out_path = Path(cmd[out_idx])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(body), encoding="utf-8")
        return subprocess.CompletedProcess(
            args=cmd, returncode=exit_code, stdout="", stderr=stderr
        )

    return _runner


# ---------------------------------------------------------------------------
# _check_cyclonedx_available
# ---------------------------------------------------------------------------


def test_check_cyclonedx_available_returns_when_module_importable() -> None:
    """The real cyclonedx_py is installed in the test env; should not raise."""
    sbom_generate._check_cyclonedx_available()


def test_check_cyclonedx_available_raises_when_module_missing() -> None:
    """Simulate cyclonedx-bom not installed via __import__ patch."""
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def _fake_import(name, *args, **kwargs):
        if name == "cyclonedx_py":
            raise ImportError("simulated missing cyclonedx_py")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_fake_import):
        with pytest.raises(sbom_generate.SbomToolError, match="cyclonedx-bom is not installed"):
            sbom_generate._check_cyclonedx_available()


# ---------------------------------------------------------------------------
# _run_cyclonedx
# ---------------------------------------------------------------------------


def test_run_cyclonedx_rejects_invalid_mode(tmp_path: Path) -> None:
    with pytest.raises(sbom_generate.SbomToolError, match="unsupported cyclonedx-bom mode"):
        sbom_generate._run_cyclonedx(
            mode="invalid",
            project_dir=tmp_path,
            out_path=tmp_path / "out.json",
        )


def test_run_cyclonedx_writes_file_in_poetry_mode(tmp_path: Path) -> None:
    out = tmp_path / "sbom.json"
    with patch("subprocess.run", side_effect=_fake_cyclonedx_run()):
        sbom_generate._run_cyclonedx(
            mode="poetry", project_dir=tmp_path, out_path=out
        )
    assert out.is_file()
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["bomFormat"] == "CycloneDX"


def test_run_cyclonedx_writes_file_in_environment_mode(tmp_path: Path) -> None:
    """Environment mode does NOT pass project_dir as positional arg."""
    out = tmp_path / "sbom.json"
    captured_cmd: list[list[str]] = []

    def _capture(cmd, **kw):  # noqa: ARG001
        captured_cmd.append(cmd)
        return _fake_cyclonedx_run()(cmd, **kw)

    with patch("subprocess.run", side_effect=_capture):
        sbom_generate._run_cyclonedx(
            mode="environment", project_dir=tmp_path, out_path=out
        )
    assert out.is_file()
    # environment mode: project_dir not in cmd
    assert str(tmp_path) not in captured_cmd[0]


def test_run_cyclonedx_propagates_nonzero_exit(tmp_path: Path) -> None:
    with patch(
        "subprocess.run",
        side_effect=_fake_cyclonedx_run(exit_code=1, stderr="bad pyproject"),
    ):
        with pytest.raises(sbom_generate.SbomToolError, match="bad pyproject"):
            sbom_generate._run_cyclonedx(
                mode="poetry", project_dir=tmp_path, out_path=tmp_path / "x.json"
            )


def test_run_cyclonedx_detects_missing_output(tmp_path: Path) -> None:
    """Simulate cyclonedx-bom exiting 0 but not writing the output file."""
    def _noop_runner(cmd, **kw):  # noqa: ARG001
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("subprocess.run", side_effect=_noop_runner):
        with pytest.raises(sbom_generate.SbomToolError, match="produced no file"):
            sbom_generate._run_cyclonedx(
                mode="poetry", project_dir=tmp_path, out_path=tmp_path / "x.json"
            )


def test_run_cyclonedx_passes_extra_args(tmp_path: Path) -> None:
    out = tmp_path / "sbom.json"
    captured: list[list[str]] = []

    def _capture(cmd, **kw):  # noqa: ARG001
        captured.append(cmd)
        return _fake_cyclonedx_run()(cmd, **kw)

    with patch("subprocess.run", side_effect=_capture):
        sbom_generate._run_cyclonedx(
            mode="poetry",
            project_dir=tmp_path,
            out_path=out,
            extra_args=["--no-dev"],
        )
    assert "--no-dev" in captured[0]


# ---------------------------------------------------------------------------
# _load_sbom -- structural validation
# ---------------------------------------------------------------------------


def test_load_sbom_happy_path(tmp_path: Path) -> None:
    path = tmp_path / "sbom.json"
    _write_minimal_sbom(path)
    body = sbom_generate._load_sbom(path)
    assert body["bomFormat"] == "CycloneDX"
    assert body["specVersion"] == "1.6"


def test_load_sbom_accepts_spec_1_5(tmp_path: Path) -> None:
    """Both 1.5 and 1.6 are supported."""
    path = tmp_path / "sbom.json"
    body = json.loads(json.dumps(_MINIMAL_SBOM))
    body["specVersion"] = "1.5"
    path.write_text(json.dumps(body), encoding="utf-8")
    out = sbom_generate._load_sbom(path)
    assert out["specVersion"] == "1.5"


def test_load_sbom_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(sbom_generate.SbomToolError, match="not found"):
        sbom_generate._load_sbom(tmp_path / "nope.json")


def test_load_sbom_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{ broken", encoding="utf-8")
    with pytest.raises(sbom_generate.SbomToolError, match="invalid JSON"):
        sbom_generate._load_sbom(path)


def test_load_sbom_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('["array", "not", "object"]', encoding="utf-8")
    with pytest.raises(sbom_generate.SbomToolError, match="must be a JSON object"):
        sbom_generate._load_sbom(path)


def test_load_sbom_rejects_missing_required_key(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"specVersion": "1.6", "components": []}', encoding="utf-8")
    with pytest.raises(sbom_generate.SbomToolError, match="missing required key"):
        sbom_generate._load_sbom(path)


def test_load_sbom_rejects_wrong_bom_format(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    body = json.loads(json.dumps(_MINIMAL_SBOM))
    body["bomFormat"] = "SPDX"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(sbom_generate.SbomToolError, match="unsupported bomFormat"):
        sbom_generate._load_sbom(path)


def test_load_sbom_rejects_wrong_spec_version(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    body = json.loads(json.dumps(_MINIMAL_SBOM))
    body["specVersion"] = "1.0"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(sbom_generate.SbomToolError, match="unsupported specVersion"):
        sbom_generate._load_sbom(path)


def test_load_sbom_rejects_non_list_components(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    body = json.loads(json.dumps(_MINIMAL_SBOM))
    body["components"] = "not-a-list"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(sbom_generate.SbomToolError, match="must be a list"):
        sbom_generate._load_sbom(path)


# ---------------------------------------------------------------------------
# _component_summary -- PEP 503 normalisation + malformed handling
# ---------------------------------------------------------------------------


def test_component_summary_normalises_names() -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "components": [
            {"name": "FastAPI", "version": "1.0"},
            {"name": "python_jose", "version": "3.0"},
            {"name": "Pytest-Cov", "version": "5.0"},
            {"name": "a___b.c", "version": "0.1"},
        ],
    }
    out = sbom_generate._component_summary(sbom)
    assert out == {
        "fastapi": "1.0",
        "python-jose": "3.0",
        "pytest-cov": "5.0",
        "a-b-c": "0.1",
    }


def test_component_summary_rejects_missing_name() -> None:
    sbom = {"components": [{"version": "1.0"}]}
    with pytest.raises(sbom_generate.SbomToolError, match="malformed component"):
        sbom_generate._component_summary(sbom)


def test_component_summary_rejects_missing_version() -> None:
    sbom = {"components": [{"name": "x"}]}
    with pytest.raises(sbom_generate.SbomToolError, match="malformed component"):
        sbom_generate._component_summary(sbom)


# ---------------------------------------------------------------------------
# Ed25519 signing helpers
# ---------------------------------------------------------------------------


def test_sbom_canonical_payload_is_deterministic() -> None:
    """Different key orderings produce the same canonical bytes."""
    sbom_a = {"a": 1, "b": [1, 2], "c": {"x": 1, "y": 2}}
    sbom_b = {"c": {"y": 2, "x": 1}, "b": [1, 2], "a": 1}
    assert (
        sbom_generate._sbom_canonical_payload(sbom_a)
        == sbom_generate._sbom_canonical_payload(sbom_b)
    )


def test_sbom_canonical_payload_is_compact() -> None:
    """No whitespace in canonical form."""
    out = sbom_generate._sbom_canonical_payload({"a": 1, "b": 2})
    assert out == b'{"a":1,"b":2}'


def test_signature_path_appends_sig_suffix(tmp_path: Path) -> None:
    p = tmp_path / "verixa.cdx.json"
    sig = sbom_generate._signature_path(p)
    assert sig.name == "verixa.cdx.json.sig"


def test_read_signature_file_happy(tmp_path: Path) -> None:
    sig_path = tmp_path / "x.sig"
    sig_path.write_text(
        json.dumps({
            "version": 1,
            "signing_key_id": "verixa-sig-test",
            "public_key": "a" * 64,
            "payload_sha256": "b" * 64,
            "signature": "c" * 128,
        }),
        encoding="utf-8",
    )
    body = sbom_generate._read_signature_file(sig_path)
    assert body["signing_key_id"] == "verixa-sig-test"


def test_read_signature_file_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(sbom_generate.SbomToolError, match="not found"):
        sbom_generate._read_signature_file(tmp_path / "no.sig")


def test_read_signature_file_rejects_invalid_json(tmp_path: Path) -> None:
    sig_path = tmp_path / "bad.sig"
    sig_path.write_text("{ broken", encoding="utf-8")
    with pytest.raises(sbom_generate.SbomToolError, match="invalid signature JSON"):
        sbom_generate._read_signature_file(sig_path)


def test_read_signature_file_rejects_non_object(tmp_path: Path) -> None:
    sig_path = tmp_path / "bad.sig"
    sig_path.write_text('["array"]', encoding="utf-8")
    with pytest.raises(sbom_generate.SbomToolError, match="must be a JSON object"):
        sbom_generate._read_signature_file(sig_path)


def test_read_signature_file_rejects_missing_key(tmp_path: Path) -> None:
    sig_path = tmp_path / "bad.sig"
    sig_path.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(sbom_generate.SbomToolError, match="missing key"):
        sbom_generate._read_signature_file(sig_path)


def test_read_signature_file_rejects_wrong_version(tmp_path: Path) -> None:
    sig_path = tmp_path / "bad.sig"
    sig_path.write_text(
        json.dumps({
            "version": 99,
            "signing_key_id": "verixa-sig-x",
            "public_key": "a" * 64,
            "payload_sha256": "b" * 64,
            "signature": "c" * 128,
        }),
        encoding="utf-8",
    )
    with pytest.raises(sbom_generate.SbomToolError, match="unsupported signature version"):
        sbom_generate._read_signature_file(sig_path)


# ---------------------------------------------------------------------------
# generate subcommand
# ---------------------------------------------------------------------------


def test_generate_subcommand_happy(tmp_path: Path, capsys) -> None:
    out = tmp_path / "sbom" / "verixa.cdx.json"
    with patch("subprocess.run", side_effect=_fake_cyclonedx_run()):
        rc = sbom_generate.main(["generate", "--out", str(out), "--mode", "environment"])
    assert rc == 0
    assert out.is_file()
    captured = capsys.readouterr()
    assert "SBOM written" in captured.out
    assert "components: 2" in captured.out


def test_generate_subcommand_handles_cyclonedx_missing(tmp_path: Path, capsys) -> None:
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def _fake_import(name, *args, **kwargs):
        if name == "cyclonedx_py":
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_fake_import):
        rc = sbom_generate.main(["generate", "--out", str(tmp_path / "x.json")])
    assert rc == 1
    captured = capsys.readouterr()
    assert "not installed" in captured.err


def test_generate_subcommand_handles_subprocess_failure(tmp_path: Path, capsys) -> None:
    out = tmp_path / "x.json"
    with patch(
        "subprocess.run",
        side_effect=_fake_cyclonedx_run(exit_code=1, stderr="boom"),
    ):
        rc = sbom_generate.main(["generate", "--out", str(out), "--mode", "environment"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "boom" in captured.err


def test_generate_subcommand_handles_invalid_output(tmp_path: Path, capsys) -> None:
    """cyclonedx-bom exits 0 but writes a structurally-invalid SBOM."""
    out = tmp_path / "x.json"

    def _bad_runner(cmd, **kw):  # noqa: ARG001
        out_idx = cmd.index("-o") + 1
        Path(cmd[out_idx]).write_text('{"not": "valid sbom"}', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("subprocess.run", side_effect=_bad_runner):
        rc = sbom_generate.main(["generate", "--out", str(out), "--mode", "environment"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid SBOM" in captured.err


# ---------------------------------------------------------------------------
# sign subcommand
# ---------------------------------------------------------------------------


def _make_keypair_files(tmp_path: Path) -> tuple[Path, Path]:
    priv_path = tmp_path / "test.priv"
    pub_path = tmp_path / "test.pub"
    kp = generate_keypair()
    priv_path.write_bytes(kp.private_key)
    pub_path.write_bytes(kp.public_key)
    return priv_path, pub_path


def test_sign_subcommand_happy(tmp_path: Path, capsys) -> None:
    sbom_path = tmp_path / "sbom.json"
    _write_minimal_sbom(sbom_path)
    priv_path, pub_path = _make_keypair_files(tmp_path)
    rc = sbom_generate.main([
        "sign", str(sbom_path),
        "--priv", str(priv_path),
        "--pub", str(pub_path),
        "--key-id", "verixa-sig-test",
    ])
    assert rc == 0
    sig_path = sbom_path.with_suffix(sbom_path.suffix + ".sig")
    assert sig_path.is_file()
    body = json.loads(sig_path.read_text(encoding="utf-8"))
    assert body["signing_key_id"] == "verixa-sig-test"
    assert len(body["signature"]) == 128  # 64 bytes hex


def test_sign_subcommand_rejects_missing_priv(tmp_path: Path, capsys) -> None:
    sbom_path = tmp_path / "sbom.json"
    _write_minimal_sbom(sbom_path)
    _, pub_path = _make_keypair_files(tmp_path)
    rc = sbom_generate.main([
        "sign", str(sbom_path),
        "--priv", str(tmp_path / "no.priv"),
        "--pub", str(pub_path),
        "--key-id", "verixa-sig-test",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "private key file not found" in captured.err


def test_sign_subcommand_rejects_missing_pub(tmp_path: Path, capsys) -> None:
    sbom_path = tmp_path / "sbom.json"
    _write_minimal_sbom(sbom_path)
    priv_path, _ = _make_keypair_files(tmp_path)
    rc = sbom_generate.main([
        "sign", str(sbom_path),
        "--priv", str(priv_path),
        "--pub", str(tmp_path / "no.pub"),
        "--key-id", "verixa-sig-test",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "public key file not found" in captured.err


def test_sign_subcommand_rejects_bad_key_id(tmp_path: Path, capsys) -> None:
    sbom_path = tmp_path / "sbom.json"
    _write_minimal_sbom(sbom_path)
    priv_path, pub_path = _make_keypair_files(tmp_path)
    rc = sbom_generate.main([
        "sign", str(sbom_path),
        "--priv", str(priv_path), "--pub", str(pub_path),
        "--key-id", "wrong-prefix",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "must start with 'verixa-sig-'" in captured.err


def test_sign_subcommand_rejects_invalid_sbom(tmp_path: Path, capsys) -> None:
    sbom_path = tmp_path / "bad.json"
    sbom_path.write_text("{ broken", encoding="utf-8")
    priv_path, pub_path = _make_keypair_files(tmp_path)
    rc = sbom_generate.main([
        "sign", str(sbom_path),
        "--priv", str(priv_path), "--pub", str(pub_path),
        "--key-id", "verixa-sig-test",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid JSON" in captured.err


def test_sign_subcommand_rejects_bad_keypair_bytes(tmp_path: Path, capsys) -> None:
    """Keypair files with wrong length cause Ed25519KeyPair to raise."""
    sbom_path = tmp_path / "sbom.json"
    _write_minimal_sbom(sbom_path)
    priv_path = tmp_path / "bad.priv"
    pub_path = tmp_path / "bad.pub"
    priv_path.write_bytes(b"\x00" * 16)  # too short
    pub_path.write_bytes(b"\x00" * 32)
    rc = sbom_generate.main([
        "sign", str(sbom_path),
        "--priv", str(priv_path), "--pub", str(pub_path),
        "--key-id", "verixa-sig-test",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "keypair invalid" in captured.err


# ---------------------------------------------------------------------------
# verify subcommand
# ---------------------------------------------------------------------------


def test_verify_subcommand_happy(tmp_path: Path, capsys) -> None:
    """Saved SBOM matches a freshly-generated SBOM -> exit 0."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    with patch("subprocess.run", side_effect=_fake_cyclonedx_run()):
        rc = sbom_generate.main(["verify", str(sbom_path), "--mode", "environment"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "VERIFIED" in captured.out


def test_verify_subcommand_detects_drift_added(tmp_path: Path, capsys) -> None:
    """Current env has a component not in saved -> exit 2."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    # Synthesise a "current" SBOM with an extra component
    current = json.loads(json.dumps(_MINIMAL_SBOM))
    current["components"].append({
        "name": "new-package", "version": "1.0",
    })
    with patch("subprocess.run", side_effect=_fake_cyclonedx_run(sbom=current)):
        rc = sbom_generate.main(["verify", str(sbom_path), "--mode", "environment"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "DRIFT DETECTED" in captured.err
    assert "added" in captured.err
    assert "new-package" in captured.err


def test_verify_subcommand_detects_drift_removed(tmp_path: Path, capsys) -> None:
    """Saved has component not in current -> exit 2."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    current = json.loads(json.dumps(_MINIMAL_SBOM))
    current["components"] = current["components"][:1]  # remove one
    with patch("subprocess.run", side_effect=_fake_cyclonedx_run(sbom=current)):
        rc = sbom_generate.main(["verify", str(sbom_path), "--mode", "environment"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "removed" in captured.err


def test_verify_subcommand_detects_drift_version_changed(
    tmp_path: Path, capsys
) -> None:
    """Same name, different version -> exit 2."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    current = json.loads(json.dumps(_MINIMAL_SBOM))
    current["components"][0]["version"] = "9.9.9"
    with patch("subprocess.run", side_effect=_fake_cyclonedx_run(sbom=current)):
        rc = sbom_generate.main(["verify", str(sbom_path), "--mode", "environment"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "version-changed" in captured.err


def test_verify_subcommand_handles_saved_load_error(tmp_path: Path, capsys) -> None:
    """Saved SBOM is broken -> exit 1 (not drift, not signature failure)."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ broken", encoding="utf-8")
    rc = sbom_generate.main(["verify", str(bad), "--mode", "environment"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid JSON" in captured.err


def test_verify_subcommand_handles_regenerate_failure(
    tmp_path: Path, capsys
) -> None:
    """cyclonedx-bom fails during regenerate -> exit 1."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    with patch(
        "subprocess.run",
        side_effect=_fake_cyclonedx_run(exit_code=1, stderr="regen failed"),
    ):
        rc = sbom_generate.main(["verify", str(sbom_path), "--mode", "environment"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "regen failed" in captured.err


def test_verify_subcommand_handles_malformed_saved_components(
    tmp_path: Path, capsys
) -> None:
    """Saved SBOM has a component missing name -> exit 1."""
    sbom_path = tmp_path / "saved.json"
    body = json.loads(json.dumps(_MINIMAL_SBOM))
    body["components"][0] = {"version": "1.0"}  # no name
    sbom_path.write_text(json.dumps(body), encoding="utf-8")
    with patch("subprocess.run", side_effect=_fake_cyclonedx_run()):
        rc = sbom_generate.main(["verify", str(sbom_path), "--mode", "environment"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "malformed component" in captured.err


def test_verify_with_signature_happy(tmp_path: Path, capsys) -> None:
    """Sign first, then verify with --check-signature -> exit 0."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    priv_path, pub_path = _make_keypair_files(tmp_path)
    # Sign
    sbom_generate.main([
        "sign", str(sbom_path),
        "--priv", str(priv_path), "--pub", str(pub_path),
        "--key-id", "verixa-sig-test",
    ])
    # Verify with signature check
    with patch("subprocess.run", side_effect=_fake_cyclonedx_run()):
        rc = sbom_generate.main([
            "verify", str(sbom_path),
            "--mode", "environment",
            "--check-signature",
        ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "SIGNATURE OK" in captured.out
    assert "VERIFIED" in captured.out


def test_verify_with_signature_detects_missing_sig(
    tmp_path: Path, capsys
) -> None:
    """--check-signature when no .sig file exists -> exit 3."""
    sbom_path = tmp_path / "unsigned.json"
    _write_minimal_sbom(sbom_path)
    rc = sbom_generate.main([
        "verify", str(sbom_path),
        "--mode", "environment",
        "--check-signature",
    ])
    assert rc == 3
    captured = capsys.readouterr()
    assert "SIGNATURE FAILURE" in captured.err


def test_verify_with_signature_detects_modified_sbom(
    tmp_path: Path, capsys
) -> None:
    """Modify SBOM after signing -> payload SHA-256 mismatch -> exit 3."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    priv_path, pub_path = _make_keypair_files(tmp_path)
    sbom_generate.main([
        "sign", str(sbom_path),
        "--priv", str(priv_path), "--pub", str(pub_path),
        "--key-id", "verixa-sig-test",
    ])
    # TAMPER: modify the SBOM
    body = json.loads(sbom_path.read_text(encoding="utf-8"))
    body["components"].append({"name": "evil-package", "version": "1.0"})
    sbom_path.write_text(json.dumps(body), encoding="utf-8")
    rc = sbom_generate.main([
        "verify", str(sbom_path),
        "--mode", "environment",
        "--check-signature",
    ])
    assert rc == 3
    captured = capsys.readouterr()
    assert "payload SHA-256 mismatch" in captured.err


def test_verify_with_signature_detects_invalid_hex(
    tmp_path: Path, capsys
) -> None:
    """Hand-crafted .sig with non-hex bytes -> exit 3."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    sig_path = sbom_path.with_suffix(sbom_path.suffix + ".sig")
    sig_path.write_text(
        json.dumps({
            "version": 1,
            "signing_key_id": "verixa-sig-test",
            "public_key": "not-hex-chars-zzz" * 4,
            "payload_sha256": "a" * 64,
            "signature": "b" * 128,
        }),
        encoding="utf-8",
    )
    rc = sbom_generate.main([
        "verify", str(sbom_path),
        "--mode", "environment",
        "--check-signature",
    ])
    assert rc == 3
    captured = capsys.readouterr()
    assert "invalid hex" in captured.err


def test_verify_with_signature_detects_wrong_key_length(
    tmp_path: Path, capsys
) -> None:
    """Hand-crafted .sig with right-hex-but-wrong-length pubkey -> exit 3."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    sig_path = sbom_path.with_suffix(sbom_path.suffix + ".sig")
    sig_path.write_text(
        json.dumps({
            "version": 1,
            "signing_key_id": "verixa-sig-test",
            "public_key": "ab" * 10,  # 20 bytes; wrong (need 32)
            "payload_sha256": "a" * 64,
            "signature": "b" * 128,
        }),
        encoding="utf-8",
    )
    rc = sbom_generate.main([
        "verify", str(sbom_path),
        "--mode", "environment",
        "--check-signature",
    ])
    assert rc == 3
    captured = capsys.readouterr()
    assert "32 bytes" in captured.err


def test_verify_with_signature_detects_forged_signature(
    tmp_path: Path, capsys
) -> None:
    """Right-shape .sig with wrong signature bytes -> Ed25519 reject -> exit 3."""
    sbom_path = tmp_path / "saved.json"
    body = _write_minimal_sbom(sbom_path)
    sig_path = sbom_path.with_suffix(sbom_path.suffix + ".sig")
    # Use a real keypair but a forged signature
    kp = generate_keypair()
    payload = sbom_generate._sbom_canonical_payload(body)
    payload_sha = hashlib.sha256(payload).hexdigest()
    sig_path.write_text(
        json.dumps({
            "version": 1,
            "signing_key_id": "verixa-sig-test",
            "public_key": kp.public_key.hex(),
            "payload_sha256": payload_sha,  # correct so we get past that check
            "signature": "00" * 64,  # bogus signature
        }),
        encoding="utf-8",
    )
    rc = sbom_generate.main([
        "verify", str(sbom_path),
        "--mode", "environment",
        "--check-signature",
    ])
    assert rc == 3
    captured = capsys.readouterr()
    assert "Ed25519" in captured.err


# ---------------------------------------------------------------------------
# show subcommand
# ---------------------------------------------------------------------------


def test_show_subcommand_happy(tmp_path: Path, capsys) -> None:
    sbom_path = tmp_path / "sbom.json"
    _write_minimal_sbom(sbom_path)
    rc = sbom_generate.main(["show", str(sbom_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "bomFormat: CycloneDX" in captured.out
    assert "specVersion: 1.6" in captured.out
    assert "components: 2" in captured.out
    assert "cyclonedx-py 7.3.0" in captured.out
    assert "(none -- run 'sign'" in captured.out


def test_show_subcommand_shows_signature_when_present(
    tmp_path: Path, capsys
) -> None:
    sbom_path = tmp_path / "sbom.json"
    _write_minimal_sbom(sbom_path)
    priv_path, pub_path = _make_keypair_files(tmp_path)
    sbom_generate.main([
        "sign", str(sbom_path),
        "--priv", str(priv_path), "--pub", str(pub_path),
        "--key-id", "verixa-sig-test",
    ])
    rc = sbom_generate.main(["show", str(sbom_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "signature:" in captured.out
    assert "verixa-sig-test" in captured.out


def test_show_subcommand_flags_invalid_signature(tmp_path: Path, capsys) -> None:
    """Side-car .sig is present but malformed -> warn but exit 0."""
    sbom_path = tmp_path / "sbom.json"
    _write_minimal_sbom(sbom_path)
    sig_path = sbom_path.with_suffix(sbom_path.suffix + ".sig")
    sig_path.write_text("{ broken", encoding="utf-8")
    rc = sbom_generate.main(["show", str(sbom_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "PRESENT BUT INVALID" in captured.out


def test_show_subcommand_rejects_missing_sbom(tmp_path: Path, capsys) -> None:
    rc = sbom_generate.main(["show", str(tmp_path / "no.json")])
    assert rc == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_show_subcommand_handles_legacy_tools_list(
    tmp_path: Path, capsys
) -> None:
    """CycloneDX 1.4 used a list-of-tools shape; tolerate it on read."""
    sbom_path = tmp_path / "sbom.json"
    body = json.loads(json.dumps(_MINIMAL_SBOM))
    body["specVersion"] = "1.5"  # 1.5 still supports both shapes
    body["metadata"]["tools"] = [
        {"name": "old-tool", "version": "1.0"}
    ]
    sbom_path.write_text(json.dumps(body), encoding="utf-8")
    rc = sbom_generate.main(["show", str(sbom_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "old-tool 1.0" in captured.out


# ---------------------------------------------------------------------------
# Additional coverage: edge paths in _cmd_verify and _cmd_show
# ---------------------------------------------------------------------------


def test_verify_subcommand_handles_cyclonedx_missing(
    tmp_path: Path, capsys
) -> None:
    """verify -> _check_cyclonedx_available failure path (distinct from generate)."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def _fake_import(name, *args, **kwargs):
        if name == "cyclonedx_py":
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_fake_import):
        rc = sbom_generate.main(["verify", str(sbom_path), "--mode", "environment"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "not installed" in captured.err


def test_verify_subcommand_handles_malformed_current_components(
    tmp_path: Path, capsys
) -> None:
    """Saved is valid but regenerated current SBOM has malformed component.

    Triggers the tmp_path.unlink() cleanup path after _component_summary
    raises on the current SBOM."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)
    # Build a "current" SBOM where a component is malformed (missing name)
    current = json.loads(json.dumps(_MINIMAL_SBOM))
    current["components"][0] = {"version": "1.0"}  # no name
    with patch("subprocess.run", side_effect=_fake_cyclonedx_run(sbom=current)):
        rc = sbom_generate.main(["verify", str(sbom_path), "--mode", "environment"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "malformed component" in captured.err
    # Confirm the tmp_path was cleaned up
    tmp_path_str = str(sbom_path.with_suffix(sbom_path.suffix + ".current"))
    assert not Path(tmp_path_str).is_file()


def test_verify_subcommand_cleans_up_tmp_on_load_failure(
    tmp_path: Path, capsys
) -> None:
    """Saved is valid; regenerate succeeds at the subprocess level but
    writes a structurally-invalid SBOM JSON; _load_sbom raises on the tmp
    file, triggering the tmp_path.unlink() cleanup branch."""
    sbom_path = tmp_path / "saved.json"
    _write_minimal_sbom(sbom_path)

    def _malformed_runner(cmd, **kw):  # noqa: ARG001
        out_idx = cmd.index("-o") + 1
        # Write structurally-invalid SBOM (no required keys)
        Path(cmd[out_idx]).write_text('{"not": "valid"}', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("subprocess.run", side_effect=_malformed_runner):
        rc = sbom_generate.main(["verify", str(sbom_path), "--mode", "environment"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "missing required key" in captured.err
    # tmp_path was cleaned up by the unlink() in the except branch
    tmp = sbom_path.with_suffix(sbom_path.suffix + ".current")
    assert not tmp.is_file()


def test_show_subcommand_handles_missing_tools_block(
    tmp_path: Path, capsys
) -> None:
    """Some SBOMs may have metadata without tools (or with tools=None);
    show MUST gracefully skip the tools listing and continue."""
    sbom_path = tmp_path / "sbom.json"
    body = json.loads(json.dumps(_MINIMAL_SBOM))
    # Remove the tools entry entirely
    del body["metadata"]["tools"]
    sbom_path.write_text(json.dumps(body), encoding="utf-8")
    rc = sbom_generate.main(["show", str(sbom_path)])
    assert rc == 0
    captured = capsys.readouterr()
    # Should still show the rest of the metadata
    assert "bomFormat: CycloneDX" in captured.out
    assert "(none -- run 'sign'" in captured.out


# ---------------------------------------------------------------------------
# Parser + main entry
# ---------------------------------------------------------------------------


def test_build_parser_returns_argument_parser() -> None:
    parser = sbom_generate.build_parser()
    assert parser.prog == "sbom_generate"


def test_main_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        sbom_generate.main([])


def test_main_is_callable() -> None:
    assert callable(sbom_generate.main)
