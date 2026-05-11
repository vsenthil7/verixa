"""CP-44 -- CycloneDX SBOM generator + signer for Verixa.

Phase-1 supply-chain artifact wrapper around the OWASP-stewarded
`cyclonedx-bom` (cyclonedx-python-lib) CLI. Generates a CycloneDX 1.6 JSON
SBOM, optionally Ed25519-signs it with the same key infrastructure used by
tools/policy_sign.py (CP-43), and supports a verify subcommand that
regenerates the current SBOM and reports drift against a saved SBOM.

Why wrap rather than re-implement:
  - OWASP CycloneDX is the canonical procurement-grade format; buyers
    expect cyclonedx-cli + cyclonedx-bom-validate compatibility, which
    a hand-rolled JSON emitter cannot guarantee
  - cyclonedx-bom 7.3.0 supports Poetry (Verixa's dep manager) directly
    via pyproject.toml -- source-of-truth deps, not as-installed
  - cyclonedx-bom 7.3.0 emits CycloneDX 1.6 (current spec) with full
    structural validation
  - Reducing our re-implementation surface reduces our supply-chain
    attack surface (the whole point of an SBOM)

Subcommands:

  generate -- run cyclonedx-bom on the Verixa project, write SBOM to disk
              (default: sbom/verixa.cdx.json)
  sign     -- Ed25519-sign an existing SBOM JSON, produce SBOM.sig file
              (uses tools/policy_sign.py infrastructure)
  verify   -- regenerate current SBOM, compare against a saved SBOM,
              optionally verify the Ed25519 signature on the saved SBOM,
              exit 2 on drift, 3 on signature failure
  show     -- pretty-print SBOM metadata + component count + tool versions

Exit codes:
  0 -- success
  1 -- invalid arguments or runtime error (cyclonedx-bom missing, etc.)
  2 -- verify detected drift between saved and current SBOM
  3 -- verify detected signature failure on the saved SBOM

Anchored to BUILD_PLAN Phase-1 supply-chain artifact gap + Phase-2
CycloneDX SBOM commitment. Ed25519 signing uses the same key custody path
documented in ADR-0008 (Vault transit in production).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from verixa_runtime.crypto.ed25519 import (
    Ed25519KeyPair,
    Ed25519SignatureError,
)
from verixa_runtime.crypto.ed25519 import (
    sign as ed25519_sign,
)
from verixa_runtime.crypto.ed25519 import (
    verify as ed25519_verify,
)

DEFAULT_SBOM_PATH: str = "sbom/verixa.cdx.json"
CYCLONEDX_MODULE: str = "cyclonedx_py"
EXPECTED_BOM_FORMAT: str = "CycloneDX"
SUPPORTED_SPEC_VERSIONS: tuple[str, ...] = ("1.5", "1.6")


class SbomToolError(RuntimeError):
    """Raised on any wrapper-level failure (cyclonedx-bom missing, bad file)."""


# ---------------------------------------------------------------------------
# cyclonedx-bom invocation
# ---------------------------------------------------------------------------


def _check_cyclonedx_available() -> None:
    """Verify cyclonedx-bom is importable. Fail fast with actionable error."""
    if shutil.which(sys.executable) is None:  # pragma: no cover -- environment guard
        raise SbomToolError(
            f"Python interpreter not on PATH: {sys.executable}"
        )
    # Lightweight import check
    try:
        __import__(CYCLONEDX_MODULE)
    except ImportError as e:
        raise SbomToolError(
            "cyclonedx-bom is not installed in the current environment. "
            "Install with: pip install cyclonedx-bom>=7.3.0"
        ) from e


def _run_cyclonedx(
    *,
    mode: str,
    project_dir: Path,
    out_path: Path,
    extra_args: list[str] | None = None,
) -> None:
    """Invoke `python -m cyclonedx_py <mode>` and write to `out_path`.

    mode must be one of: 'poetry', 'environment', 'requirements'.

    Raises SbomToolError if the underlying tool exits non-zero.
    """
    if mode not in ("poetry", "environment", "requirements"):
        raise SbomToolError(f"unsupported cyclonedx-bom mode: {mode!r}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd: list[str] = [
        sys.executable, "-m", CYCLONEDX_MODULE, mode,
        "--of", "json",
        "-o", str(out_path),
    ]
    if mode == "poetry":
        cmd.append(str(project_dir))
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(  # noqa: S603 -- args are constructed from validated inputs
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SbomToolError(
            f"cyclonedx-bom failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    if not out_path.is_file():
        raise SbomToolError(
            f"cyclonedx-bom succeeded but produced no file: {out_path}"
        )


# ---------------------------------------------------------------------------
# SBOM JSON validation + structural read
# ---------------------------------------------------------------------------


def _load_sbom(path: Path) -> dict[str, Any]:
    """Read + structurally validate a CycloneDX SBOM JSON file."""
    if not path.is_file():
        raise SbomToolError(f"SBOM file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SbomToolError(f"invalid JSON in {path}: {e}") from e
    if not isinstance(raw, dict):
        raise SbomToolError(f"SBOM root must be a JSON object: {path}")
    for required in ("bomFormat", "specVersion", "components"):
        if required not in raw:
            raise SbomToolError(
                f"SBOM missing required key {required!r}: {path}"
            )
    if raw["bomFormat"] != EXPECTED_BOM_FORMAT:
        raise SbomToolError(
            f"unsupported bomFormat {raw['bomFormat']!r}: "
            f"expected {EXPECTED_BOM_FORMAT!r}"
        )
    if raw["specVersion"] not in SUPPORTED_SPEC_VERSIONS:
        raise SbomToolError(
            f"unsupported specVersion {raw['specVersion']!r}: "
            f"expected one of {SUPPORTED_SPEC_VERSIONS!r}"
        )
    if not isinstance(raw["components"], list):
        raise SbomToolError("SBOM components must be a list")
    return raw


def _component_summary(sbom: dict[str, Any]) -> dict[str, str]:
    """Flatten {normalised-name: version} from an SBOM's components."""
    out: dict[str, str] = {}
    for c in sbom["components"]:
        name = c.get("name")
        version = c.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise SbomToolError(
                f"malformed component (missing name/version): {c!r}"
            )
        # PEP 503 normalisation: lowercase + collapse runs of [-_.]+ to '-'
        norm = name.lower()
        for ch in "._":
            norm = norm.replace(ch, "-")
        while "--" in norm:
            norm = norm.replace("--", "-")
        out[norm] = version
    return out


# ---------------------------------------------------------------------------
# Ed25519 signing -- reuses tools/policy_sign.py key file format
# ---------------------------------------------------------------------------


def _sbom_canonical_payload(sbom: dict[str, Any]) -> bytes:
    """Canonical JSON of the SBOM for signing.

    Sorted keys, no whitespace, UTF-8 bytes. Mirrors the
    verixa_runtime.policy.signing canonical-payload approach so that any
    formatting / re-pretty-printing of the SBOM file on disk doesn't break
    signature verification (the signature is over the canonical form, not
    the on-disk JSON bytes).
    """
    return json.dumps(
        sbom, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _load_keypair(priv_path: Path, pub_path: Path) -> Ed25519KeyPair:
    """Load a 32+32-byte raw keypair (same format as policy_sign.py)."""
    return Ed25519KeyPair(
        private_key=priv_path.read_bytes(),
        public_key=pub_path.read_bytes(),
    )


def _signature_path(sbom_path: Path) -> Path:
    """Side-car .sig file lives alongside the SBOM."""
    return sbom_path.with_suffix(sbom_path.suffix + ".sig")


def _write_signature_file(
    sig_path: Path,
    *,
    signing_key_id: str,
    public_key_hex: str,
    payload_sha256_hex: str,
    signature_hex: str,
) -> None:
    """Write the side-car JSON signature artifact."""
    body = {
        "version": 1,
        "signing_key_id": signing_key_id,
        "public_key": public_key_hex,
        "payload_sha256": payload_sha256_hex,
        "signature": signature_hex,
    }
    sig_path.write_text(
        json.dumps(body, indent=2, sort_keys=True), encoding="utf-8"
    )


def _read_signature_file(sig_path: Path) -> dict[str, str]:
    """Read + structurally validate a .sig sidecar."""
    if not sig_path.is_file():
        raise SbomToolError(f"signature file not found: {sig_path}")
    try:
        raw = json.loads(sig_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SbomToolError(f"invalid signature JSON: {e}") from e
    if not isinstance(raw, dict):
        raise SbomToolError("signature root must be a JSON object")
    for required in (
        "version", "signing_key_id", "public_key",
        "payload_sha256", "signature",
    ):
        if required not in raw:
            raise SbomToolError(
                f"signature missing key {required!r}"
            )
    if raw["version"] != 1:
        raise SbomToolError(
            f"unsupported signature version {raw['version']!r}"
        )
    return raw


# ---------------------------------------------------------------------------
# Subcommand: generate
# ---------------------------------------------------------------------------


def _cmd_generate(args: argparse.Namespace) -> int:
    """Run cyclonedx-bom and write the SBOM to disk."""
    try:
        _check_cyclonedx_available()
    except SbomToolError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    project_dir = Path(args.project_dir).resolve()
    out_path = Path(args.out)

    try:
        _run_cyclonedx(
            mode=args.mode,
            project_dir=project_dir,
            out_path=out_path,
        )
    except SbomToolError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Validate what we just produced
    try:
        sbom = _load_sbom(out_path)
    except SbomToolError as e:
        print(
            f"ERROR: cyclonedx-bom produced an invalid SBOM: {e}",
            file=sys.stderr,
        )
        return 1

    print(f"SBOM written: {out_path}")
    print(f"  bomFormat: {sbom['bomFormat']}")
    print(f"  specVersion: {sbom['specVersion']}")
    print(f"  components: {len(sbom['components'])}")
    print(f"  mode: {args.mode}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: sign
# ---------------------------------------------------------------------------


def _cmd_sign(args: argparse.Namespace) -> int:
    """Ed25519-sign an existing SBOM JSON; write .sig sidecar."""
    sbom_path = Path(args.sbom_path)
    priv_path = Path(args.priv)
    pub_path = Path(args.pub)
    if not priv_path.is_file():
        print(
            f"ERROR: private key file not found: {priv_path}",
            file=sys.stderr,
        )
        return 1
    if not pub_path.is_file():
        print(
            f"ERROR: public key file not found: {pub_path}",
            file=sys.stderr,
        )
        return 1
    if not args.key_id.startswith("verixa-sig-"):
        print(
            f"ERROR: --key-id must start with 'verixa-sig-' "
            f"(got {args.key_id!r})",
            file=sys.stderr,
        )
        return 1
    try:
        sbom = _load_sbom(sbom_path)
    except SbomToolError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    try:
        kp = _load_keypair(priv_path, pub_path)
    except ValueError as e:
        print(f"ERROR: keypair invalid: {e}", file=sys.stderr)
        return 1

    payload = _sbom_canonical_payload(sbom)
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    signature = ed25519_sign(kp.private_key, payload)

    sig_path = _signature_path(sbom_path)
    _write_signature_file(
        sig_path,
        signing_key_id=args.key_id,
        public_key_hex=kp.public_key.hex(),
        payload_sha256_hex=payload_sha256,
        signature_hex=signature.hex(),
    )
    print(f"Signed SBOM {sbom_path} -> {sig_path}")
    print(f"  key-id: {args.key_id}")
    print(f"  public key: {kp.public_key.hex()}")
    print(f"  payload SHA-256: {payload_sha256}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: verify
# ---------------------------------------------------------------------------


def _cmd_verify(args: argparse.Namespace) -> int:
    """Regenerate current SBOM, compare against saved, optionally verify sig.

    Exit codes:
      0 -- saved SBOM matches current env (and signature valid if checked)
      1 -- runtime error
      2 -- drift detected
      3 -- signature verification failed
    """
    try:
        _check_cyclonedx_available()
    except SbomToolError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    saved_path = Path(args.sbom_path)
    try:
        saved = _load_sbom(saved_path)
    except SbomToolError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # If --check-signature, verify the saved SBOM's sidecar BEFORE drift check
    if args.check_signature:
        sig_path = _signature_path(saved_path)
        try:
            sig_body = _read_signature_file(sig_path)
        except SbomToolError as e:
            print(f"SIGNATURE FAILURE: {e}", file=sys.stderr)
            return 3
        try:
            public_key = bytes.fromhex(sig_body["public_key"])
            signature = bytes.fromhex(sig_body["signature"])
        except ValueError as e:
            print(
                f"SIGNATURE FAILURE: invalid hex in signature: {e}",
                file=sys.stderr,
            )
            return 3
        if len(public_key) != 32 or len(signature) != 64:
            print(
                "SIGNATURE FAILURE: public_key must be 32 bytes, "
                "signature must be 64 bytes",
                file=sys.stderr,
            )
            return 3
        payload = _sbom_canonical_payload(saved)
        actual_sha = hashlib.sha256(payload).hexdigest()
        if actual_sha != sig_body["payload_sha256"]:
            print(
                f"SIGNATURE FAILURE: payload SHA-256 mismatch "
                f"(saved-claims={sig_body['payload_sha256']}, "
                f"actual={actual_sha}); SBOM has been modified "
                f"since signing",
                file=sys.stderr,
            )
            return 3
        try:
            ed25519_verify(public_key, payload, signature)
        except Ed25519SignatureError as e:
            print(
                f"SIGNATURE FAILURE: Ed25519 verification rejected: {e}",
                file=sys.stderr,
            )
            return 3
        print(
            f"SIGNATURE OK: {sig_path} (key-id={sig_body['signing_key_id']})"
        )

    # Regenerate the current SBOM into a temp path
    project_dir = Path(args.project_dir).resolve()
    tmp_path = saved_path.with_suffix(saved_path.suffix + ".current")
    try:
        _run_cyclonedx(
            mode=args.mode,
            project_dir=project_dir,
            out_path=tmp_path,
        )
        current = _load_sbom(tmp_path)
    except SbomToolError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if tmp_path.is_file():
            tmp_path.unlink()
        return 1

    try:
        saved_summary = _component_summary(saved)
        current_summary = _component_summary(current)
    except SbomToolError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        tmp_path.unlink()
        return 1
    tmp_path.unlink()

    saved_keys = set(saved_summary.keys())
    current_keys = set(current_summary.keys())
    added = current_keys - saved_keys
    removed = saved_keys - current_keys
    changed = {
        k: (saved_summary[k], current_summary[k])
        for k in saved_keys & current_keys
        if saved_summary[k] != current_summary[k]
    }

    if not added and not removed and not changed:
        print(
            f"VERIFIED: SBOM matches current environment "
            f"({len(saved_summary)} components)"
        )
        return 0

    print("DRIFT DETECTED:", file=sys.stderr)
    if added:
        print(f"  added ({len(added)}):", file=sys.stderr)
        for n in sorted(added):
            print(f"    + {n}@{current_summary[n]}", file=sys.stderr)
    if removed:
        print(f"  removed ({len(removed)}):", file=sys.stderr)
        for n in sorted(removed):
            print(f"    - {n}@{saved_summary[n]}", file=sys.stderr)
    if changed:
        print(f"  version-changed ({len(changed)}):", file=sys.stderr)
        for n, (old, new) in sorted(changed.items()):
            print(f"    ~ {n}: {old} -> {new}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# Subcommand: show
# ---------------------------------------------------------------------------


def _cmd_show(args: argparse.Namespace) -> int:
    """Pretty-print SBOM metadata + component count."""
    sbom_path = Path(args.sbom_path)
    try:
        sbom = _load_sbom(sbom_path)
    except SbomToolError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    metadata = sbom.get("metadata", {})
    print(f"SBOM: {sbom_path}")
    print(f"  bomFormat: {sbom['bomFormat']}")
    print(f"  specVersion: {sbom['specVersion']}")
    print(f"  serialNumber: {sbom.get('serialNumber', '-')}")
    print(f"  timestamp: {metadata.get('timestamp', '-')}")
    print(f"  components: {len(sbom['components'])}")
    tools = metadata.get("tools")
    if isinstance(tools, dict):
        # CycloneDX 1.5+ tools-as-object shape
        components = tools.get("components") or []
        for t in components:
            print(
                f"    tool: {t.get('name', '-')} "
                f"{t.get('version', '-')}"
            )
    elif isinstance(tools, list):
        # CycloneDX 1.4 legacy tools-as-list
        for t in tools:
            print(
                f"    tool: {t.get('name', '-')} "
                f"{t.get('version', '-')}"
            )
    sig_path = _signature_path(sbom_path)
    if sig_path.is_file():
        try:
            sig_body = _read_signature_file(sig_path)
            print(f"  signature: {sig_path}")
            print(f"    key-id: {sig_body['signing_key_id']}")
        except SbomToolError as e:
            print(f"  signature: PRESENT BUT INVALID -- {e}")
    else:
        print("  signature: (none -- run 'sign' to create one)")
    return 0


# ---------------------------------------------------------------------------
# Argparse plumbing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sbom_generate",
        description=(
            "Generate, sign, and verify CycloneDX SBOMs for the Verixa "
            "project. Wraps OWASP cyclonedx-bom with Ed25519 signing "
            "using the same key infrastructure as tools/policy_sign.py "
            "(CP-43)."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # generate
    p_gen = sub.add_parser(
        "generate", help="run cyclonedx-bom + write SBOM to disk"
    )
    p_gen.add_argument(
        "--out", default=DEFAULT_SBOM_PATH,
        help=f"output path (default: {DEFAULT_SBOM_PATH})",
    )
    p_gen.add_argument(
        "--mode",
        default="poetry",
        choices=["poetry", "environment", "requirements"],
        help="cyclonedx-bom subcommand (default: poetry)",
    )
    p_gen.add_argument(
        "--project-dir", default=".",
        help="project directory containing pyproject.toml (default: cwd)",
    )
    p_gen.set_defaults(func=_cmd_generate)

    # sign
    p_sign = sub.add_parser(
        "sign",
        help="Ed25519-sign an existing SBOM JSON; write .sig sidecar",
    )
    p_sign.add_argument("sbom_path", help="path to SBOM JSON")
    p_sign.add_argument("--priv", required=True, help="private key file (32 bytes raw)")
    p_sign.add_argument("--pub", required=True, help="public key file (32 bytes raw)")
    p_sign.add_argument(
        "--key-id", required=True,
        help="key identifier; must start with 'verixa-sig-'",
    )
    p_sign.set_defaults(func=_cmd_sign)

    # verify
    p_ver = sub.add_parser(
        "verify",
        help=(
            "regenerate SBOM, compare to saved (exit 2 on drift); "
            "with --check-signature also verify Ed25519 (exit 3 on sig fail)"
        ),
    )
    p_ver.add_argument("sbom_path", help="path to saved SBOM JSON")
    p_ver.add_argument(
        "--mode", default="poetry",
        choices=["poetry", "environment", "requirements"],
    )
    p_ver.add_argument(
        "--project-dir", default=".",
        help="project directory containing pyproject.toml (default: cwd)",
    )
    p_ver.add_argument(
        "--check-signature", action="store_true",
        help="also verify the .sig sidecar Ed25519 signature",
    )
    p_ver.set_defaults(func=_cmd_verify)

    # show
    p_show = sub.add_parser(
        "show",
        help="pretty-print SBOM metadata + signature status",
    )
    p_show.add_argument("sbom_path", help="path to SBOM JSON")
    p_show.set_defaults(func=_cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
