"""Policy bundle signing -- Ed25519-signed manifest of file SHA-256 hashes.

Mirrors the OPA bundle-signing convention (a ``.signatures.json`` file
listing per-file hashes + an outer signature) but uses Verixa's
per-tenant Ed25519 signing keys (built in CP-4.1).

Signed bundle layout:

    policies/<pack>/
      .manifest                   (existing OPA bundle manifest)
      .signatures.json            (this module produces / verifies)
      <name>.rego                 (one or more .rego files)
      fixtures/
        <name>_fixtures.json

The ``.signatures.json`` shape:

    {
      "version": 1,
      "signing_key_id": "verixa-sig-<short>",
      "public_key": "<hex 64>",       # 32-byte Ed25519 pubkey, hex
      "files": {
        "<relative_path>": "<sha256-hex 64>",
        ...
      },
      "signature": "<hex 128>"        # Ed25519 over canonical-serialised
                                       # files mapping
    }

The signed payload is the canonical JSON of the ``files`` dict (sorted
keys, no whitespace) -- *not* the entire ``.signatures.json`` content.
This keeps signature verification deterministic regardless of how the
JSON file is formatted on disk.

Note on dead code: ``json.loads`` always produces ``str`` keys for JSON
objects (per RFC 8259), so we don't defensively re-check key types --
that branch is unreachable and would never gain coverage.

Public API:
  - ``BundleSignaturesError``       raised on tamper / malformed / mismatch
  - ``BundleSignatures``            frozen dataclass of the parsed file
  - ``compute_bundle_file_hashes``  walk a bundle dir hashing every file
  - ``sign_bundle``                 produce + write ``.signatures.json``
  - ``verify_bundle_signatures``    load + verify ``.signatures.json``
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from verixa_runtime.crypto.ed25519 import (
    Ed25519KeyPair,
    Ed25519SignatureError,
    sign as ed25519_sign,
    verify as ed25519_verify,
)

SIGNATURES_FILENAME: Final[str] = ".signatures.json"
SIGNATURES_VERSION: Final[int] = 1


class BundleSignaturesError(ValueError):
    """Raised on any signing / verification failure."""


@dataclass(frozen=True, slots=True)
class BundleSignatures:
    """Parsed contents of ``.signatures.json``."""

    version: int
    signing_key_id: str
    public_key: bytes  # 32 bytes
    files: dict[str, str]  # relative_path -> sha256-hex
    signature: bytes  # 64 bytes


def _bundle_files_for_signing(bundle_dir: Path) -> list[Path]:
    """Return every file under bundle_dir that's part of the signed payload.

    Excludes:
      - ``.signatures.json`` itself (would be circular)
      - hidden files starting with ``.`` *other than* ``.manifest``
        (so .signatures.json and any future . files are excluded by
        default; .manifest is explicitly included)

    Files are returned in deterministic POSIX-style relative-path order
    so signing and verifying always hash the same payload regardless of
    OS file-listing order.
    """
    bundle_dir = bundle_dir.resolve()
    out: list[Path] = []
    for path in bundle_dir.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(bundle_dir)
        # Always include .manifest; exclude .signatures.json; exclude
        # anything else that starts with a dot.
        rel_str = rel.as_posix()
        first_segment = rel_str.split("/", 1)[0]
        if first_segment == SIGNATURES_FILENAME:
            continue
        if first_segment.startswith(".") and first_segment != ".manifest":
            continue
        out.append(path)
    out.sort(key=lambda p: p.relative_to(bundle_dir).as_posix())
    return out


def compute_bundle_file_hashes(bundle_dir: Path) -> dict[str, str]:
    """Return ``{relative_posix_path: sha256_hex}`` for every signed file."""
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir():
        raise BundleSignaturesError(f"not a directory: {bundle_dir}")
    out: dict[str, str] = {}
    for f in _bundle_files_for_signing(bundle_dir):
        rel = f.relative_to(bundle_dir.resolve()).as_posix()
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        out[rel] = digest
    return out


def _canonical_payload(files_map: dict[str, str]) -> bytes:
    """Canonical JSON of the files map -- the bytes we sign / verify."""
    return json.dumps(
        files_map, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sign_bundle(
    bundle_dir: Path,
    *,
    keypair: Ed25519KeyPair,
    signing_key_id: str,
) -> Path:
    """Sign ``bundle_dir`` and write ``.signatures.json`` into it.

    Returns the Path of the written file. Overwrites any existing
    ``.signatures.json`` (CP-12 deployment workflow re-signs on every
    bundle update).
    """
    if not signing_key_id.startswith("verixa-sig-"):
        raise BundleSignaturesError(
            "signing_key_id must start with 'verixa-sig-'"
        )
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir():
        raise BundleSignaturesError(f"not a directory: {bundle_dir}")

    files_map = compute_bundle_file_hashes(bundle_dir)
    payload = _canonical_payload(files_map)
    signature = ed25519_sign(keypair.private_key, payload)

    body: dict[str, object] = {
        "version": SIGNATURES_VERSION,
        "signing_key_id": signing_key_id,
        "public_key": keypair.public_key.hex(),
        "files": files_map,
        "signature": signature.hex(),
    }
    out_path = bundle_dir / SIGNATURES_FILENAME
    out_path.write_text(
        json.dumps(body, indent=2, sort_keys=True), encoding="utf-8"
    )
    return out_path


def _parse_signatures_file(path: Path) -> BundleSignatures:
    """Read + structurally validate ``.signatures.json``."""
    if not path.is_file():
        raise BundleSignaturesError(
            f"missing {SIGNATURES_FILENAME}: {path}"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BundleSignaturesError(
            f"invalid JSON in {path}: {e}"
        ) from e
    if not isinstance(raw, dict):
        raise BundleSignaturesError(
            f"signatures root must be a JSON object: {path}"
        )
    for required in (
        "version",
        "signing_key_id",
        "public_key",
        "files",
        "signature",
    ):
        if required not in raw:
            raise BundleSignaturesError(
                f"signatures missing key {required!r}: {path}"
            )
    if raw["version"] != SIGNATURES_VERSION:
        raise BundleSignaturesError(
            f"unsupported signatures version {raw['version']}: "
            f"expected {SIGNATURES_VERSION}"
        )
    if not isinstance(raw["signing_key_id"], str) or not raw[
        "signing_key_id"
    ].startswith("verixa-sig-"):
        raise BundleSignaturesError(
            "signing_key_id must be a string starting with 'verixa-sig-'"
        )
    try:
        public_key = bytes.fromhex(raw["public_key"])
        signature = bytes.fromhex(raw["signature"])
    except ValueError as e:
        raise BundleSignaturesError(
            f"public_key / signature is not valid hex in {path}"
        ) from e
    if len(public_key) != 32:
        raise BundleSignaturesError(
            f"public_key must be 32 bytes, got {len(public_key)}"
        )
    if len(signature) != 64:
        raise BundleSignaturesError(
            f"signature must be 64 bytes, got {len(signature)}"
        )
    files = raw["files"]
    if not isinstance(files, dict):
        raise BundleSignaturesError(
            f"files must be a JSON object: {path}"
        )
    # JSON object keys are always strings (RFC 8259); we only validate the
    # values here.
    for rel, digest in files.items():
        if not isinstance(digest, str) or len(digest) != 64:
            raise BundleSignaturesError(
                f"files[{rel!r}] hash must be 64-hex string"
            )
    return BundleSignatures(
        version=int(raw["version"]),
        signing_key_id=str(raw["signing_key_id"]),
        public_key=public_key,
        files={str(k): str(v) for k, v in files.items()},
        signature=signature,
    )


def verify_bundle_signatures(bundle_dir: Path) -> BundleSignatures:
    """Verify a signed bundle. Raise ``BundleSignaturesError`` on failure.

    Checks:
      1. ``.signatures.json`` parses cleanly + has correct shape
      2. Ed25519 signature verifies under the embedded public key over
         the canonical-serialised files map
      3. Every file currently on disk under bundle_dir is in the files
         map and its SHA-256 matches (any drift = tampered file)
      4. There are no extra files on disk that aren't in files map
         (added file = tampered bundle)
    """
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir():
        raise BundleSignaturesError(f"not a directory: {bundle_dir}")
    sig_path = bundle_dir / SIGNATURES_FILENAME
    parsed = _parse_signatures_file(sig_path)

    # 2. Signature over the claimed files map
    payload = _canonical_payload(parsed.files)
    try:
        ed25519_verify(parsed.public_key, payload, parsed.signature)
    except Ed25519SignatureError as e:
        raise BundleSignaturesError(
            "Ed25519 signature verification failed for bundle "
            f"{bundle_dir.name}"
        ) from e

    # 3. + 4. Disk vs claimed files map (recompute disk hashes)
    disk_hashes = compute_bundle_file_hashes(bundle_dir)
    claimed_set = set(parsed.files.keys())
    disk_set = set(disk_hashes.keys())
    missing = claimed_set - disk_set
    extra = disk_set - claimed_set
    if missing:
        raise BundleSignaturesError(
            f"signed files missing from disk: {sorted(missing)}"
        )
    if extra:
        raise BundleSignaturesError(
            f"unsigned files present on disk: {sorted(extra)}"
        )
    for rel, claimed_hash in parsed.files.items():
        if disk_hashes[rel] != claimed_hash:
            raise BundleSignaturesError(
                f"file content drift: {rel} hash mismatch"
            )

    return parsed
