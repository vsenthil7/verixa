"""CP-46 -- HTTP integration tests for the /v1/control/policy/bundles routes.

Anchored to Phase-1 carry-forward "OPA bundle distribution server" gap that
CP-43 (signing CLI) + CP-45 (BundleServer module) left for HTTP wiring.

Tests use FastAPI TestClient against a real wired-up app. The bundle_server
is provided via a tmp_path fixture that lays down a signed bundle on disk
so the routes exercise the actual signing + serving chain end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from verixa_control_plane.routes import (
    build_default_state,
    create_app_with_state,
)
from verixa_runtime.crypto.ed25519 import generate_keypair
from verixa_runtime.policy import (
    BundleServer,
    sign_bundle,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_signed_bundle(
    bundle_dir: Path,
    *,
    rego: str = "package verixa.demo\n\ndefault allow := false\n",
    key_id: str = "verixa-sig-test",
) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / ".manifest").write_text(
        '{"revision": "test-1", "roots": ["verixa"]}\n', encoding="utf-8"
    )
    (bundle_dir / "demo.rego").write_text(rego, encoding="utf-8")
    kp = generate_keypair()
    sign_bundle(bundle_dir, keypair=kp, signing_key_id=key_id)


@pytest.fixture
def signed_policies_root(tmp_path: Path) -> Path:
    """Create a policies root with 2 signed bundles + 1 unsigned."""
    _build_signed_bundle(tmp_path / "core")
    _build_signed_bundle(tmp_path / "fs-pack")
    # Unsigned bundle (should be excluded from list, refused on fetch)
    unsigned = tmp_path / "unsigned"
    unsigned.mkdir()
    (unsigned / ".manifest").write_text(
        '{"revision": "x", "roots": ["verixa"]}\n', encoding="utf-8"
    )
    (unsigned / "x.rego").write_text(
        "package verixa.x\ndefault allow := false\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def client_with_bundles(signed_policies_root: Path) -> TestClient:
    state = build_default_state()
    state.bundle_server = BundleServer(signed_policies_root)
    app = create_app_with_state(state)
    return TestClient(app)


@pytest.fixture
def client_no_bundles() -> TestClient:
    """A client whose state has bundle_server=None (Phase-0 default)."""
    state = build_default_state()
    app = create_app_with_state(state)
    return TestClient(app)


# ---------------------------------------------------------------------------
# /v1/control/policy/bundles -- list
# ---------------------------------------------------------------------------


def test_bundles_list_returns_signed_bundles(
    client_with_bundles: TestClient,
) -> None:
    r = client_with_bundles.get("/v1/control/policy/bundles")
    assert r.status_code == 200
    body = r.json()
    assert "bundles" in body
    # Only signed bundles; unsigned excluded
    assert sorted(body["bundles"]) == ["core", "fs-pack"]


def test_bundles_list_returns_503_when_disabled(
    client_no_bundles: TestClient,
) -> None:
    r = client_no_bundles.get("/v1/control/policy/bundles")
    assert r.status_code == 503
    assert "error" in r.json()


# ---------------------------------------------------------------------------
# /v1/control/policy/bundles/{name} -- fetch happy path
# ---------------------------------------------------------------------------


def test_bundles_fetch_returns_gzipped_tar(
    client_with_bundles: TestClient,
) -> None:
    r = client_with_bundles.get("/v1/control/policy/bundles/core")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/gzip"
    assert r.headers["etag"].startswith('"')
    assert (
        r.headers["x-verixa-bundle-signing-key-id"] == "verixa-sig-test"
    )
    # gzip magic bytes
    assert r.content[:2] == b"\x1f\x8b"


def test_bundles_fetch_etag_is_stable_across_calls(
    client_with_bundles: TestClient,
) -> None:
    r1 = client_with_bundles.get("/v1/control/policy/bundles/core")
    r2 = client_with_bundles.get("/v1/control/policy/bundles/core")
    assert r1.headers["etag"] == r2.headers["etag"]


def test_bundles_fetch_different_bundles_have_different_etags(
    client_with_bundles: TestClient,
) -> None:
    r1 = client_with_bundles.get("/v1/control/policy/bundles/core")
    r2 = client_with_bundles.get("/v1/control/policy/bundles/fs-pack")
    assert r1.headers["etag"] != r2.headers["etag"]


# ---------------------------------------------------------------------------
# If-None-Match -> 304 Not Modified
# ---------------------------------------------------------------------------


def test_bundles_fetch_returns_304_on_matching_if_none_match(
    client_with_bundles: TestClient,
) -> None:
    r1 = client_with_bundles.get("/v1/control/policy/bundles/core")
    etag = r1.headers["etag"]
    r2 = client_with_bundles.get(
        "/v1/control/policy/bundles/core",
        headers={"If-None-Match": etag},
    )
    assert r2.status_code == 304
    assert r2.headers["etag"] == etag
    assert r2.content == b""  # 304 has no body


def test_bundles_fetch_returns_200_on_mismatching_if_none_match(
    client_with_bundles: TestClient,
) -> None:
    r = client_with_bundles.get(
        "/v1/control/policy/bundles/core",
        headers={"If-None-Match": '"some-other-etag"'},
    )
    assert r.status_code == 200
    assert r.content[:2] == b"\x1f\x8b"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_bundles_fetch_returns_400_on_invalid_name(
    client_with_bundles: TestClient,
) -> None:
    """Uppercase name fails the allow-list."""
    r = client_with_bundles.get("/v1/control/policy/bundles/Core")
    assert r.status_code == 400
    assert "allow-list" in r.json()["error"]


def test_bundles_fetch_returns_404_on_missing_bundle(
    client_with_bundles: TestClient,
) -> None:
    r = client_with_bundles.get("/v1/control/policy/bundles/nope")
    assert r.status_code == 404
    assert "not found" in r.json()["error"]


def test_bundles_fetch_returns_409_on_unsigned_bundle(
    client_with_bundles: TestClient,
) -> None:
    """The 'unsigned' fixture directory exists in the policies root but
    has no .signatures.json -> 409 Conflict."""
    r = client_with_bundles.get("/v1/control/policy/bundles/unsigned")
    assert r.status_code == 409
    assert "signatures.json" in r.json()["error"]


def test_bundles_fetch_returns_409_on_tampered_bundle(
    client_with_bundles: TestClient, signed_policies_root: Path
) -> None:
    """If a rego file is modified after signing, signature verification
    fails -> 409 Conflict."""
    # Tamper the core bundle
    (signed_policies_root / "core" / "demo.rego").write_text(
        "package verixa.demo\n\ndefault allow := true  # attacker\n",
        encoding="utf-8",
    )
    r = client_with_bundles.get("/v1/control/policy/bundles/core")
    assert r.status_code == 409
    assert "verification failed" in r.json()["error"]


def test_bundles_fetch_returns_503_when_disabled(
    client_no_bundles: TestClient,
) -> None:
    r = client_no_bundles.get("/v1/control/policy/bundles/core")
    assert r.status_code == 503
    assert "error" in r.json()


# ---------------------------------------------------------------------------
# OpenAPI surface
# ---------------------------------------------------------------------------


def test_openapi_includes_bundle_routes(
    client_with_bundles: TestClient,
) -> None:
    spec = client_with_bundles.get("/openapi.json").json()
    assert "/v1/control/policy/bundles" in spec["paths"]
    assert "/v1/control/policy/bundles/{name}" in spec["paths"]


# ---------------------------------------------------------------------------
# Path-traversal hardening
# ---------------------------------------------------------------------------


def test_bundles_fetch_blocks_path_traversal_attempts(
    client_with_bundles: TestClient,
) -> None:
    """Even if a malicious caller constructs '../etc/passwd' style names,
    Starlette's path param decoding + the BundleServer's allow-list
    must reject. Note: FastAPI URL-decodes path params, so we test
    against names that *survive* decoding but should still fail."""
    # URL-encoded slashes get decoded by Starlette before path matching,
    # so '../etc/passwd' style names hit a 404 from FastAPI's routing
    # layer rather than the bundle server. Either outcome is correct:
    # the request never reaches a filesystem read.
    r = client_with_bundles.get(
        "/v1/control/policy/bundles/..%2Fetc%2Fpasswd"
    )
    assert r.status_code in (400, 404), (
        f"path-traversal attempt MUST NOT succeed; got {r.status_code}"
    )
    assert r.status_code != 200


def test_bundles_fetch_blocks_uppercase(
    client_with_bundles: TestClient,
) -> None:
    r = client_with_bundles.get("/v1/control/policy/bundles/FS-PACK")
    assert r.status_code == 400


def test_bundles_fetch_blocks_dots(
    client_with_bundles: TestClient,
) -> None:
    r = client_with_bundles.get("/v1/control/policy/bundles/core.bundle")
    assert r.status_code == 400
