"""pytest suite for verixa_runtime.policy.signing (CP-8.4).

Builds synthetic bundles in tmp_path, signs them with a fresh tenant
keypair (via CP-4.4 bootstrap_tenant), and verifies every code path:
  - happy round-trip
  - signing rejects bad signing_key_id prefix
  - signing rejects non-directory targets
  - verify rejects missing .signatures.json
  - verify rejects malformed JSON / missing keys / wrong version
  - verify rejects bad hex / wrong public_key length / wrong signature length
  - verify rejects non-object 'files'
  - verify rejects non-string keys / non-64-hex hashes in 'files'
  - verify catches signature tamper
  - verify catches file content tamper
  - verify catches missing file (was signed but deleted)
  - verify catches extra file (added after signing)
  - hidden files starting with '.' (other than .manifest) are excluded
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

from verixa_runtime.crypto.key_bootstrap import bootstrap_tenant
from verixa_runtime.policy.signing import (
    SIGNATURES_FILENAME,
    SIGNATURES_VERSION,
    BundleSignatures,
    BundleSignaturesError,
    compute_bundle_file_hashes,
    sign_bundle,
    verify_bundle_signatures,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle(tmp_path: Path) -> Path:
    """Create a minimal valid bundle directory."""
    bundle = tmp_path / "fake_pack"
    bundle.mkdir()
    (bundle / ".manifest").write_text(
        json.dumps({"revision": "v1", "roots": ["x"]}), encoding="utf-8"
    )
    (bundle / "policy_a.rego").write_text(
        "package verixa.x\n\ndefault decision := \"pass\"\n",
        encoding="utf-8",
    )
    (bundle / "fixtures").mkdir()
    (bundle / "fixtures" / "a.json").write_text(
        json.dumps({"fixtures": []}), encoding="utf-8"
    )
    return bundle


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    return _make_bundle(tmp_path)


@pytest.fixture
def keybundle():
    return bootstrap_tenant(uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))


# ---------------------------------------------------------------------------
# compute_bundle_file_hashes
# ---------------------------------------------------------------------------


def test_compute_hashes_returns_sha256_per_file(bundle: Path) -> None:
    hashes = compute_bundle_file_hashes(bundle)
    assert ".manifest" in hashes
    assert "policy_a.rego" in hashes
    assert "fixtures/a.json" in hashes
    for digest in hashes.values():
        assert len(digest) == 64
        int(digest, 16)  # raises ValueError if not hex


def test_compute_hashes_excludes_signatures_file(
    bundle: Path, keybundle
) -> None:
    sign_bundle(
        bundle, keypair=keybundle.signing_keypair, signing_key_id=keybundle.signing_key_id
    )
    hashes = compute_bundle_file_hashes(bundle)
    assert SIGNATURES_FILENAME not in hashes


def test_compute_hashes_excludes_hidden_files_other_than_manifest(
    bundle: Path,
) -> None:
    """Files / dirs starting with '.' are excluded except .manifest."""
    (bundle / ".hidden_other").write_text("ignore", encoding="utf-8")
    (bundle / ".cache").mkdir()
    (bundle / ".cache" / "x.txt").write_text("ignore", encoding="utf-8")
    hashes = compute_bundle_file_hashes(bundle)
    assert ".manifest" in hashes  # explicitly included
    assert ".hidden_other" not in hashes
    assert all(not k.startswith(".cache") for k in hashes)


def test_compute_hashes_rejects_non_directory(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi")
    with pytest.raises(BundleSignaturesError, match="not a directory"):
        compute_bundle_file_hashes(f)


def test_compute_hashes_matches_actual_sha256(bundle: Path) -> None:
    """Sanity: hash matches the literal SHA-256 of the file bytes."""
    hashes = compute_bundle_file_hashes(bundle)
    expected = hashlib.sha256(
        (bundle / "policy_a.rego").read_bytes()
    ).hexdigest()
    assert hashes["policy_a.rego"] == expected


# ---------------------------------------------------------------------------
# sign_bundle -- happy path + input validation
# ---------------------------------------------------------------------------


def test_sign_writes_signatures_json(bundle: Path, keybundle) -> None:
    out = sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    assert out == bundle / SIGNATURES_FILENAME
    assert out.is_file()
    body = json.loads(out.read_text())
    assert body["version"] == SIGNATURES_VERSION
    assert body["signing_key_id"] == keybundle.signing_key_id
    assert body["public_key"] == keybundle.public_key.hex()
    assert "files" in body
    assert "signature" in body


def test_sign_overwrites_existing_signatures_file(
    bundle: Path, keybundle
) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    # Modify a file then re-sign; the second .signatures.json must reflect new hash
    (bundle / "policy_a.rego").write_text(
        "package verixa.x\n# changed\n", encoding="utf-8"
    )
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    expected = hashlib.sha256(
        (bundle / "policy_a.rego").read_bytes()
    ).hexdigest()
    assert body["files"]["policy_a.rego"] == expected


def test_sign_rejects_bad_signing_key_id(bundle: Path, keybundle) -> None:
    with pytest.raises(
        BundleSignaturesError, match="must start with 'verixa-sig-'"
    ):
        sign_bundle(
            bundle,
            keypair=keybundle.signing_keypair,
            signing_key_id="other-prefix-abc",
        )


def test_sign_rejects_non_directory(tmp_path: Path, keybundle) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi")
    with pytest.raises(BundleSignaturesError, match="not a directory"):
        sign_bundle(
            f,
            keypair=keybundle.signing_keypair,
            signing_key_id=keybundle.signing_key_id,
        )


# ---------------------------------------------------------------------------
# verify_bundle_signatures -- happy round-trip
# ---------------------------------------------------------------------------


def test_verify_round_trip(bundle: Path, keybundle) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    parsed = verify_bundle_signatures(bundle)
    assert isinstance(parsed, BundleSignatures)
    assert parsed.signing_key_id == keybundle.signing_key_id
    assert parsed.public_key == keybundle.public_key
    assert parsed.version == SIGNATURES_VERSION


def test_verify_rejects_non_directory(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi")
    with pytest.raises(BundleSignaturesError, match="not a directory"):
        verify_bundle_signatures(f)


def test_verify_rejects_missing_signatures_file(bundle: Path) -> None:
    with pytest.raises(BundleSignaturesError, match=f"missing {SIGNATURES_FILENAME}"):
        verify_bundle_signatures(bundle)


def test_verify_rejects_invalid_json(bundle: Path) -> None:
    (bundle / SIGNATURES_FILENAME).write_text("not json", encoding="utf-8")
    with pytest.raises(BundleSignaturesError, match="invalid JSON"):
        verify_bundle_signatures(bundle)


def test_verify_rejects_non_object_root(bundle: Path) -> None:
    (bundle / SIGNATURES_FILENAME).write_text(
        json.dumps([1, 2]), encoding="utf-8"
    )
    with pytest.raises(BundleSignaturesError, match="must be a JSON object"):
        verify_bundle_signatures(bundle)


@pytest.mark.parametrize(
    "missing_key",
    ["version", "signing_key_id", "public_key", "files", "signature"],
)
def test_verify_rejects_missing_required_key(
    bundle: Path, keybundle, missing_key: str
) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    body.pop(missing_key)
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(
        BundleSignaturesError, match=f"missing key '{missing_key}'"
    ):
        verify_bundle_signatures(bundle)


def test_verify_rejects_unsupported_version(bundle: Path, keybundle) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    body["version"] = 99
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(BundleSignaturesError, match="unsupported signatures version"):
        verify_bundle_signatures(bundle)


def test_verify_rejects_bad_signing_key_id(bundle: Path, keybundle) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    body["signing_key_id"] = "other-prefix"
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(BundleSignaturesError, match="verixa-sig-"):
        verify_bundle_signatures(bundle)


def test_verify_rejects_non_string_signing_key_id(
    bundle: Path, keybundle
) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    body["signing_key_id"] = 123
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(BundleSignaturesError, match="must be a string"):
        verify_bundle_signatures(bundle)


def test_verify_rejects_invalid_hex(bundle: Path, keybundle) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    body["public_key"] = "ZZ" * 32
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(BundleSignaturesError, match="not valid hex"):
        verify_bundle_signatures(bundle)


def test_verify_rejects_wrong_public_key_length(
    bundle: Path, keybundle
) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    body["public_key"] = "ab" * 16  # 16 bytes, want 32
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(BundleSignaturesError, match="public_key must be 32 bytes"):
        verify_bundle_signatures(bundle)


def test_verify_rejects_wrong_signature_length(
    bundle: Path, keybundle
) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    body["signature"] = "ab" * 16  # 16 bytes, want 64
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(BundleSignaturesError, match="signature must be 64 bytes"):
        verify_bundle_signatures(bundle)


def test_verify_rejects_non_object_files(bundle: Path, keybundle) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    body["files"] = ["a", "b"]
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(BundleSignaturesError, match="files must be a JSON object"):
        verify_bundle_signatures(bundle)


def test_verify_rejects_non_64_hash_in_files(bundle: Path, keybundle) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    body["files"]["policy_a.rego"] = "abcd"  # too short
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(BundleSignaturesError, match="hash must be 64-hex"):
        verify_bundle_signatures(bundle)


# ---------------------------------------------------------------------------
# Tamper detection (the actual security guarantees)
# ---------------------------------------------------------------------------


def test_verify_detects_signature_tamper(bundle: Path, keybundle) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    sig = bytes.fromhex(body["signature"])
    bad = bytearray(sig)
    bad[0] ^= 0x01
    body["signature"] = bytes(bad).hex()
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(
        BundleSignaturesError, match="signature verification failed"
    ):
        verify_bundle_signatures(bundle)


def test_verify_detects_file_content_drift(bundle: Path, keybundle) -> None:
    """Modify a .rego after signing -> hash mismatch detected."""
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    (bundle / "policy_a.rego").write_text(
        "package verixa.x\n# tampered\n", encoding="utf-8"
    )
    with pytest.raises(BundleSignaturesError, match="hash mismatch"):
        verify_bundle_signatures(bundle)


def test_verify_detects_signed_file_deleted(
    bundle: Path, keybundle
) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    (bundle / "policy_a.rego").unlink()
    with pytest.raises(
        BundleSignaturesError, match="missing from disk"
    ):
        verify_bundle_signatures(bundle)


def test_verify_detects_extra_file_added(bundle: Path, keybundle) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    (bundle / "policy_b.rego").write_text(
        "package verixa.y\n", encoding="utf-8"
    )
    with pytest.raises(
        BundleSignaturesError, match="unsigned files present"
    ):
        verify_bundle_signatures(bundle)


def test_verify_detects_wrong_keypair(bundle: Path, keybundle) -> None:
    """A second tenant's keypair signs the bundle; first tenant's pubkey
    in .signatures.json -> signature won't verify."""
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    other = bootstrap_tenant(uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    body = json.loads((bundle / SIGNATURES_FILENAME).read_text())
    # Replace signature with one made by a different key over the SAME files map
    from verixa_runtime.crypto.ed25519 import sign as ed25519_sign

    canonical = json.dumps(
        body["files"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    new_sig = ed25519_sign(other.signing_keypair.private_key, canonical)
    body["signature"] = new_sig.hex()
    # Public_key still claims original tenant -> mismatch
    (bundle / SIGNATURES_FILENAME).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(
        BundleSignaturesError, match="signature verification failed"
    ):
        verify_bundle_signatures(bundle)


# ---------------------------------------------------------------------------
# BundleSignatures + reexports
# ---------------------------------------------------------------------------


def test_bundle_signatures_is_frozen(bundle: Path, keybundle) -> None:
    sign_bundle(
        bundle,
        keypair=keybundle.signing_keypair,
        signing_key_id=keybundle.signing_key_id,
    )
    parsed = verify_bundle_signatures(bundle)
    with pytest.raises((AttributeError, Exception)):
        parsed.version = 99  # type: ignore[misc]


def test_constants() -> None:
    assert SIGNATURES_FILENAME == ".signatures.json"
    assert SIGNATURES_VERSION == 1


def test_policy_package_reexports_signing() -> None:
    from verixa_runtime import policy

    for name in (
        "BundleSignatures",
        "BundleSignaturesError",
        "SIGNATURES_FILENAME",
        "SIGNATURES_VERSION",
        "compute_bundle_file_hashes",
        "sign_bundle",
        "verify_bundle_signatures",
    ):
        assert hasattr(policy, name), f"policy package missing {name}"
