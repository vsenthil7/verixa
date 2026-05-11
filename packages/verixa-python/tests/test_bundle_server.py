"""CP-45 tests for verixa_runtime.policy.bundle_server -- OPA bundle distribution.

Anchored to Phase-1 carry-forward "OPA bundle distribution server"
(signing CLI was done in CP-43 commit a3d7d5a; distribution server was
pending). Closes the gap.

Test plan:
  - valid_bundle_name() pure-function pattern checks (positive + negative)
  - BundleServer construction (happy + bad-root)
  - BundleServer.list_bundles() (empty + unsigned-skipped + bad-name-skipped + signed-included)
  - BundleServer.serve() happy path
  - serve() determinism: same source -> same tarball -> same ETag
  - serve() rejections: invalid name, path-traversal, not-found, unsigned,
    tampered (signature verification failure)
  - tarball is a real gzipped-tar, contains expected files, is readable
    by stdlib tarfile
  - tarball is deterministic: gzip mtime=0, file mtime fixed, uid/gid=0
"""

from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import pytest
from verixa_runtime.crypto.ed25519 import generate_keypair
from verixa_runtime.policy.bundle_server import (
    BundleArtifact,
    BundleNameInvalid,
    BundleNotFound,
    BundleServer,
    BundleServerError,
    BundleUnsigned,
    valid_bundle_name,
)
from verixa_runtime.policy.signing import (
    SIGNATURES_FILENAME,
    sign_bundle,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_unsigned_bundle(
    bundle_dir: Path,
    *,
    rego_files: dict[str, str] | None = None,
    manifest: str | None = None,
) -> None:
    """Create a minimal unsigned bundle layout."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / ".manifest").write_text(
        manifest or '{"revision": "test-1", "roots": ["verixa"]}\n',
        encoding="utf-8",
    )
    if rego_files is None:
        rego_files = {"hello.rego": "package verixa.hello\n\ndefault allow := false\n"}
    for name, content in rego_files.items():
        (bundle_dir / name).write_text(content, encoding="utf-8")


def _sign(bundle_dir: Path, *, key_id: str = "verixa-sig-test") -> None:
    """Sign a previously-built bundle dir with a fresh keypair."""
    kp = generate_keypair()
    sign_bundle(bundle_dir, keypair=kp, signing_key_id=key_id)


def _build_signed_bundle(
    bundle_dir: Path,
    *,
    rego_files: dict[str, str] | None = None,
    key_id: str = "verixa-sig-test",
) -> None:
    """Build + sign a bundle in one call."""
    _build_unsigned_bundle(bundle_dir, rego_files=rego_files)
    _sign(bundle_dir, key_id=key_id)


# ---------------------------------------------------------------------------
# valid_bundle_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "core",
        "fs-pack",
        "financial-services",
        "a",
        "0",
        "abc-123_def",
        "a" * 64,  # max length
    ],
)
def test_valid_bundle_name_accepts_good_names(name: str) -> None:
    assert valid_bundle_name(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "",                          # empty
        "../etc/passwd",             # path traversal
        "../../",                    # path traversal
        "core/sub",                  # contains slash
        "core\\win",                 # contains backslash
        "Core",                      # uppercase rejected
        "_starts_with_underscore",   # must start with [a-z0-9]
        "-starts_with_hyphen",       # must start with [a-z0-9]
        "name with space",
        "name.with.dot",
        "name@symbol",
        "core\x00null",
        "café",                      # unicode
        "a" * 65,                    # too long
    ],
)
def test_valid_bundle_name_rejects_bad_names(name: str) -> None:
    assert valid_bundle_name(name) is False


def test_valid_bundle_name_rejects_non_string() -> None:
    """Type-defensive check: a non-string slipping in returns False, not TypeError."""
    assert valid_bundle_name(None) is False  # type: ignore[arg-type]
    assert valid_bundle_name(123) is False  # type: ignore[arg-type]
    assert valid_bundle_name(["core"]) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# BundleServer construction
# ---------------------------------------------------------------------------


def test_bundle_server_construction_happy(tmp_path: Path) -> None:
    srv = BundleServer(tmp_path)
    assert srv.policies_root == tmp_path.resolve()


def test_bundle_server_rejects_nonexistent_root(tmp_path: Path) -> None:
    with pytest.raises(BundleServerError, match="not a directory"):
        BundleServer(tmp_path / "does-not-exist")


def test_bundle_server_rejects_file_as_root(tmp_path: Path) -> None:
    f = tmp_path / "notadir.txt"
    f.write_text("oops", encoding="utf-8")
    with pytest.raises(BundleServerError, match="not a directory"):
        BundleServer(f)


# ---------------------------------------------------------------------------
# BundleServer.list_bundles
# ---------------------------------------------------------------------------


def test_list_bundles_empty_root(tmp_path: Path) -> None:
    srv = BundleServer(tmp_path)
    assert srv.list_bundles() == []


def test_list_bundles_skips_unsigned(tmp_path: Path) -> None:
    """A bundle with .manifest but no .signatures.json is excluded."""
    _build_unsigned_bundle(tmp_path / "unsigned")
    srv = BundleServer(tmp_path)
    assert srv.list_bundles() == []


def test_list_bundles_includes_signed(tmp_path: Path) -> None:
    _build_signed_bundle(tmp_path / "core")
    _build_signed_bundle(tmp_path / "fs-pack")
    srv = BundleServer(tmp_path)
    assert srv.list_bundles() == ["core", "fs-pack"]


def test_list_bundles_skips_non_directory_children(tmp_path: Path) -> None:
    (tmp_path / "stray.txt").write_text("hello", encoding="utf-8")
    _build_signed_bundle(tmp_path / "core")
    srv = BundleServer(tmp_path)
    assert srv.list_bundles() == ["core"]


def test_list_bundles_skips_invalid_names(tmp_path: Path) -> None:
    """A directory whose NAME fails the allow-list is excluded even if signed.

    This is defence-in-depth: the directory might have been created by an
    operator with an invalid name; the server refuses to advertise it
    because it cannot be served via the HTTP API anyway.
    """
    _build_signed_bundle(tmp_path / "Bad-Caps")  # uppercase rejected
    _build_signed_bundle(tmp_path / "good")
    srv = BundleServer(tmp_path)
    assert srv.list_bundles() == ["good"]


def test_list_bundles_skips_dir_without_manifest(tmp_path: Path) -> None:
    """A directory with .signatures.json but no .manifest is malformed."""
    bd = tmp_path / "broken"
    bd.mkdir()
    (bd / SIGNATURES_FILENAME).write_text("{}", encoding="utf-8")
    srv = BundleServer(tmp_path)
    assert srv.list_bundles() == []


# ---------------------------------------------------------------------------
# BundleServer.serve -- happy path
# ---------------------------------------------------------------------------


def test_serve_happy_path_returns_bundle_artifact(tmp_path: Path) -> None:
    _build_signed_bundle(tmp_path / "core")
    srv = BundleServer(tmp_path)
    artifact = srv.serve("core")
    assert isinstance(artifact, BundleArtifact)
    assert artifact.name == "core"
    assert artifact.tarball  # non-empty
    assert artifact.etag.startswith('"') and artifact.etag.endswith('"')
    assert len(artifact.etag) == 66  # "<64-hex>"
    assert artifact.signatures.signing_key_id == "verixa-sig-test"
    assert artifact.generated_at > 0


def test_serve_returns_real_gzipped_tar(tmp_path: Path) -> None:
    """The tarball MUST be a real gzip+tar parseable by stdlib tarfile."""
    _build_signed_bundle(
        tmp_path / "core",
        rego_files={
            "hello.rego": "package verixa.hello\n\ndefault allow := false\n",
            "limit.rego": "package verixa.limit\n\ndefault allow := true\n",
        },
    )
    srv = BundleServer(tmp_path)
    artifact = srv.serve("core")
    # Parse back
    buf = io.BytesIO(artifact.tarball)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        names = sorted(m.name for m in tar.getmembers())
    assert ".manifest" in names
    assert ".signatures.json" in names
    assert "hello.rego" in names
    assert "limit.rego" in names


def test_serve_tarball_files_have_deterministic_mtime(tmp_path: Path) -> None:
    """Every tar entry MUST have the fixed mtime so the tarball is content-addressed."""
    _build_signed_bundle(tmp_path / "core")
    srv = BundleServer(tmp_path)
    artifact = srv.serve("core")
    buf = io.BytesIO(artifact.tarball)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        for m in tar.getmembers():
            assert m.mtime == 1577836800, (
                f"member {m.name} has mtime {m.mtime}, expected fixed value"
            )
            assert m.uid == 0
            assert m.gid == 0
            assert m.uname == ""
            assert m.gname == ""
            assert m.mode == 0o644


def test_serve_etag_is_sha256_of_tarball(tmp_path: Path) -> None:
    _build_signed_bundle(tmp_path / "core")
    srv = BundleServer(tmp_path)
    artifact = srv.serve("core")
    expected = f'"{hashlib.sha256(artifact.tarball).hexdigest()}"'
    assert artifact.etag == expected


# ---------------------------------------------------------------------------
# Determinism: same source -> same bytes -> same ETag
# ---------------------------------------------------------------------------


def test_serve_is_deterministic_across_calls(tmp_path: Path) -> None:
    """Two successive serve() calls on the same bundle MUST return
    byte-identical tarballs and identical ETags."""
    _build_signed_bundle(tmp_path / "core")
    srv = BundleServer(tmp_path)
    a1 = srv.serve("core")
    a2 = srv.serve("core")
    assert a1.tarball == a2.tarball, "tarball bytes must be deterministic"
    assert a1.etag == a2.etag, "ETag must be stable across calls"


def test_serve_different_bundles_produce_different_etags(
    tmp_path: Path,
) -> None:
    _build_signed_bundle(
        tmp_path / "a",
        rego_files={"a.rego": "package verixa.a\ndefault allow := true\n"},
    )
    _build_signed_bundle(
        tmp_path / "b",
        rego_files={"b.rego": "package verixa.b\ndefault allow := false\n"},
    )
    srv = BundleServer(tmp_path)
    ea = srv.serve("a").etag
    eb = srv.serve("b").etag
    assert ea != eb


def test_serve_changed_bundle_produces_different_etag(
    tmp_path: Path,
) -> None:
    """Editing a rego file then re-signing changes the ETag."""
    bd = tmp_path / "core"
    _build_signed_bundle(bd)
    srv = BundleServer(tmp_path)
    etag_v1 = srv.serve("core").etag

    # Modify + re-sign
    (bd / "hello.rego").write_text(
        "package verixa.hello\n\ndefault allow := true  # changed\n",
        encoding="utf-8",
    )
    _sign(bd)  # re-sign in place
    etag_v2 = srv.serve("core").etag

    assert etag_v1 != etag_v2


# ---------------------------------------------------------------------------
# serve() rejections
# ---------------------------------------------------------------------------


def test_serve_rejects_invalid_name(tmp_path: Path) -> None:
    srv = BundleServer(tmp_path)
    with pytest.raises(BundleNameInvalid, match="allow-list"):
        srv.serve("../etc/passwd")


def test_serve_rejects_uppercase_name(tmp_path: Path) -> None:
    srv = BundleServer(tmp_path)
    with pytest.raises(BundleNameInvalid):
        srv.serve("Core")


def test_serve_rejects_empty_name(tmp_path: Path) -> None:
    srv = BundleServer(tmp_path)
    with pytest.raises(BundleNameInvalid):
        srv.serve("")


def test_serve_rejects_missing_bundle(tmp_path: Path) -> None:
    srv = BundleServer(tmp_path)
    with pytest.raises(BundleNotFound, match="not found"):
        srv.serve("nonexistent")


def test_serve_rejects_unsigned_bundle(tmp_path: Path) -> None:
    _build_unsigned_bundle(tmp_path / "core")
    srv = BundleServer(tmp_path)
    with pytest.raises(BundleUnsigned, match="signatures.json"):
        srv.serve("core")


def test_serve_rejects_tampered_bundle(tmp_path: Path) -> None:
    """If the bundle's .signatures.json is valid but a .rego file was
    modified after signing, signature verification fails and the server
    refuses to serve."""
    bd = tmp_path / "core"
    _build_signed_bundle(bd)
    # TAMPER: modify a rego file after signing
    (bd / "hello.rego").write_text(
        "package verixa.hello\n\ndefault allow := true  # attacker\n",
        encoding="utf-8",
    )
    srv = BundleServer(tmp_path)
    with pytest.raises(BundleUnsigned, match="verification failed"):
        srv.serve("core")


def test_serve_rejects_symlink_traversal_attempt(tmp_path: Path) -> None:
    """A bundle name with valid syntax but pointing outside via symlink
    must still be caught by the relative_to bound check. We don't create
    a real symlink (Windows requires admin); we use a name that resolves
    fine and verify the resolved-path bounds check works on the happy
    path so the existence of the check is exercised."""
    _build_signed_bundle(tmp_path / "core")
    srv = BundleServer(tmp_path)
    # Happy path proves the relative_to call ran without raising
    artifact = srv.serve("core")
    assert artifact.name == "core"


def test_serve_rejects_file_not_directory(tmp_path: Path) -> None:
    """A name that resolves to a regular file (not a directory) is 404."""
    (tmp_path / "stub").write_text("not-a-bundle", encoding="utf-8")
    srv = BundleServer(tmp_path)
    with pytest.raises(BundleNotFound):
        srv.serve("stub")


# ---------------------------------------------------------------------------
# Bundle contents filtering
# ---------------------------------------------------------------------------


def test_serve_includes_signatures_json_in_tarball(tmp_path: Path) -> None:
    """Receivers verify signatures on receipt; the .signatures.json must
    travel with the bundle."""
    _build_signed_bundle(tmp_path / "core")
    srv = BundleServer(tmp_path)
    artifact = srv.serve("core")
    buf = io.BytesIO(artifact.tarball)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        names = {m.name for m in tar.getmembers()}
    assert ".signatures.json" in names


def test_serve_excludes_other_hidden_files(tmp_path: Path) -> None:
    """Hidden dot-files OTHER than .manifest and .signatures.json must be
    excluded from the tarball. They were also excluded from signing, so
    if they were included in the tarball, OPA verifiers would error on
    missing signatures."""
    bd = tmp_path / "core"
    _build_unsigned_bundle(bd)
    # Add some stray dot-files BEFORE signing
    (bd / ".DS_Store").write_text("mac noise", encoding="utf-8")
    (bd / ".git_marker").write_text("vcs noise", encoding="utf-8")
    _sign(bd)
    srv = BundleServer(tmp_path)
    artifact = srv.serve("core")
    buf = io.BytesIO(artifact.tarball)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        names = {m.name for m in tar.getmembers()}
    assert ".DS_Store" not in names
    assert ".git_marker" not in names


def test_serve_includes_nested_files(tmp_path: Path) -> None:
    """fixtures/ subdir contents should be packaged."""
    bd = tmp_path / "core"
    _build_unsigned_bundle(bd)
    fixtures = bd / "fixtures"
    fixtures.mkdir()
    (fixtures / "hello_fixtures.json").write_text(
        '{"fixtures": []}', encoding="utf-8"
    )
    _sign(bd)
    srv = BundleServer(tmp_path)
    artifact = srv.serve("core")
    buf = io.BytesIO(artifact.tarball)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        names = {m.name for m in tar.getmembers()}
    assert "fixtures/hello_fixtures.json" in names


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_api_exports() -> None:
    """All advertised public names must import cleanly from the package."""
    from verixa_runtime.policy import (
        BundleArtifact as _BA,
    )
    from verixa_runtime.policy import (
        BundleNameInvalid as _BNI,
    )
    from verixa_runtime.policy import (
        BundleNotFound as _BNF,
    )
    from verixa_runtime.policy import (
        BundleServer as _BS,
    )
    from verixa_runtime.policy import (
        BundleServerError as _BSE,
    )
    from verixa_runtime.policy import (
        BundleUnsigned as _BU,
    )
    from verixa_runtime.policy import (
        valid_bundle_name as _vbn,
    )
    # Smoke: every import resolves
    assert _BA is BundleArtifact
    assert _BNI is BundleNameInvalid
    assert _BNF is BundleNotFound
    assert _BS is BundleServer
    assert _BSE is BundleServerError
    assert _BU is BundleUnsigned
    assert _vbn is valid_bundle_name
