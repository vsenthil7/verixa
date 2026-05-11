"""CP-43 -- policy_sign.py CLI for Ed25519-signing and verifying OPA policy bundles.

Wraps the Phase-0 `verixa_runtime.policy.signing` module behind a CLI so
operators can:

  - Sign a bundle directory in-place (writes .signatures.json)
  - Verify a bundle's signatures (returns 0 on valid, non-zero on tamper)
  - Generate a fresh signing keypair (writes priv+pub to files)
  - Show the verifying public key + key-id of a signed bundle (audit)

This is the operator-facing Phase-1 deliverable for OPA bundle signing
infrastructure. The cryptographic primitive (`sign_bundle`/`verify_bundle_signatures`)
already existed in Phase 0; this CLI is the wrapper that makes it usable
from a deployment pipeline.

Subcommands:

    python -m tools.policy_sign generate-key \
        --out keys/dev.priv --pub-out keys/dev.pub --key-id verixa-sig-dev
    python -m tools.policy_sign sign policies/fs_pack/ \
        --priv keys/dev.priv --pub keys/dev.pub --key-id verixa-sig-dev
    python -m tools.policy_sign verify policies/fs_pack/
    python -m tools.policy_sign show policies/fs_pack/

All paths are relative to CWD or absolute. The signing key is loaded
from a file containing the 32-byte raw private key (NOT PEM); use
generate-key to produce one in the correct format. For production use,
the private key should live in HashiCorp Vault transit (per ADR-0008);
this CLI is for development + CI signing.

NEVER print the private key bytes to stdout. The show subcommand only
displays public key + key-id.

Exit codes:
  0  -- success
  1  -- invalid arguments or runtime error
  2  -- signature verification FAILED (bundle is tampered or unsigned)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verixa_runtime.crypto.ed25519 import (
    Ed25519KeyPair,
    generate_keypair,
)
from verixa_runtime.policy.signing import (
    BundleSignaturesError,
    sign_bundle,
    verify_bundle_signatures,
)


def _cmd_generate_key(args: argparse.Namespace) -> int:
    """Generate a fresh Ed25519 keypair and write priv+pub to files.

    Refuses to overwrite existing files (operators should rotate via
    explicit delete-then-generate to avoid accidental key loss).
    """
    priv_path = Path(args.out)
    pub_path = Path(args.pub_out)
    if priv_path.exists():
        print(
            f"ERROR: private key file already exists: {priv_path}; "
            f"refusing to overwrite (delete it first to rotate)",
            file=sys.stderr,
        )
        return 1
    if pub_path.exists():
        print(
            f"ERROR: public key file already exists: {pub_path}; "
            f"refusing to overwrite",
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
    kp = generate_keypair()
    priv_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    priv_path.write_bytes(kp.private_key)
    pub_path.write_bytes(kp.public_key)
    # POSIX: restrict private key to owner-only
    try:
        priv_path.chmod(0o600)
    except (OSError, NotImplementedError):  # pragma: no cover -- Windows chmod is best-effort
        # Windows chmod is best-effort; private key restriction is a
        # filesystem-ACL concern there. Untested by design since the
        # chmod path is platform-dependent and the failure is benign.
        pass
    print(f"Generated keypair for {args.key_id}:")
    print(f"  private key -> {priv_path}")
    print(f"  public key  -> {pub_path} ({kp.public_key.hex()})")
    return 0


def _load_keypair(priv_path: Path, pub_path: Path) -> Ed25519KeyPair:
    """Load a keypair from two raw-bytes files."""
    priv = priv_path.read_bytes()
    pub = pub_path.read_bytes()
    return Ed25519KeyPair(private_key=priv, public_key=pub)


def _cmd_sign(args: argparse.Namespace) -> int:
    """Sign a bundle directory in-place."""
    bundle_dir = Path(args.bundle_dir)
    priv_path = Path(args.priv)
    pub_path = Path(args.pub)
    if not bundle_dir.is_dir():
        print(
            f"ERROR: not a directory: {bundle_dir}", file=sys.stderr
        )
        return 1
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
    try:
        kp = _load_keypair(priv_path, pub_path)
    except ValueError as e:
        print(f"ERROR: keypair invalid: {e}", file=sys.stderr)
        return 1
    try:
        out = sign_bundle(
            bundle_dir, keypair=kp, signing_key_id=args.key_id
        )
    except BundleSignaturesError as e:
        print(f"ERROR: signing failed: {e}", file=sys.stderr)
        return 1
    print(f"Signed bundle {bundle_dir} -> {out}")
    print(f"  key-id: {args.key_id}")
    print(f"  public key: {kp.public_key.hex()}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    """Verify a signed bundle's signature + file hashes.

    Exit code 2 indicates tamper detection (distinct from 1 for
    invalid args / runtime errors); CI pipelines can use this to
    treat tamper as a critical security failure."""
    bundle_dir = Path(args.bundle_dir)
    if not bundle_dir.is_dir():
        print(
            f"ERROR: not a directory: {bundle_dir}", file=sys.stderr
        )
        return 1
    try:
        sigs = verify_bundle_signatures(bundle_dir)
    except BundleSignaturesError as e:
        print(
            f"VERIFICATION FAILED for {bundle_dir}: {e}", file=sys.stderr
        )
        return 2
    print(f"VERIFIED bundle {bundle_dir}")
    print(f"  key-id: {sigs.signing_key_id}")
    print(f"  public key: {sigs.public_key.hex()}")
    print(f"  files: {len(sigs.files)} signed")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    """Show key-id + public key of a signed bundle (no verification)."""
    bundle_dir = Path(args.bundle_dir)
    if not bundle_dir.is_dir():
        print(
            f"ERROR: not a directory: {bundle_dir}", file=sys.stderr
        )
        return 1
    try:
        sigs = verify_bundle_signatures(bundle_dir)
    except BundleSignaturesError as e:
        print(
            f"ERROR: cannot show -- bundle invalid: {e}",
            file=sys.stderr,
        )
        return 1
    print(f"Bundle: {bundle_dir}")
    print(f"key-id: {sigs.signing_key_id}")
    print(f"public-key: {sigs.public_key.hex()}")
    print(f"files-signed: {len(sigs.files)}")
    for rel in sorted(sigs.files):
        print(f"  {rel}  {sigs.files[rel]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="policy_sign",
        description=(
            "CLI for Ed25519-signing and verifying OPA policy bundles. "
            "Wraps verixa_runtime.policy.signing for operator + CI use."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # generate-key
    p_gen = sub.add_parser(
        "generate-key", help="generate a fresh Ed25519 keypair"
    )
    p_gen.add_argument(
        "--out", required=True, help="path for private key file (32 bytes raw)"
    )
    p_gen.add_argument(
        "--pub-out", required=True, help="path for public key file (32 bytes raw)"
    )
    p_gen.add_argument(
        "--key-id",
        required=True,
        help="key identifier; must start with 'verixa-sig-'",
    )
    p_gen.set_defaults(func=_cmd_generate_key)

    # sign
    p_sign = sub.add_parser(
        "sign", help="sign a bundle directory in-place (writes .signatures.json)"
    )
    p_sign.add_argument("bundle_dir", help="path to bundle directory")
    p_sign.add_argument("--priv", required=True, help="path to private key file")
    p_sign.add_argument("--pub", required=True, help="path to public key file")
    p_sign.add_argument(
        "--key-id",
        required=True,
        help="key identifier; must start with 'verixa-sig-'",
    )
    p_sign.set_defaults(func=_cmd_sign)

    # verify
    p_ver = sub.add_parser(
        "verify",
        help="verify a signed bundle (exit 2 on tamper, 0 on valid)",
    )
    p_ver.add_argument("bundle_dir", help="path to bundle directory")
    p_ver.set_defaults(func=_cmd_verify)

    # show
    p_show = sub.add_parser(
        "show",
        help="show key-id + public key + file list of a signed bundle",
    )
    p_show.add_argument("bundle_dir", help="path to bundle directory")
    p_show.set_defaults(func=_cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
