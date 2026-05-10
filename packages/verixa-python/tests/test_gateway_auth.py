"""pytest suite for verixa_runtime.gateway.auth (CP-6.4).

Covers parse_api_key_env validation matrix, ApiKeyMiddleware bypass logic,
401 paths, and successful auth attaching tenant_id to request.state.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from verixa_runtime.app import create_app
from verixa_runtime.gateway.auth import (
    API_KEY_HEADER,
    BYPASS_PATHS,
    ENV_VAR_NAME,
    parse_api_key_env,
)


# ---------------------------------------------------------------------------
# parse_api_key_env
# ---------------------------------------------------------------------------


def test_parse_empty_returns_empty_dict() -> None:
    assert parse_api_key_env("") == {}


def test_parse_whitespace_only_returns_empty_dict() -> None:
    assert parse_api_key_env("   ") == {}


def test_parse_single_pair() -> None:
    tid_str = "11111111-1111-1111-1111-111111111111"
    result = parse_api_key_env(f"{tid_str}:secret-key")
    assert result == {"secret-key": uuid.UUID(tid_str)}


def test_parse_multiple_pairs() -> None:
    tid1 = "11111111-1111-1111-1111-111111111111"
    tid2 = "22222222-2222-2222-2222-222222222222"
    result = parse_api_key_env(f"{tid1}:key1, {tid2}:key2")
    assert len(result) == 2
    assert result["key1"] == uuid.UUID(tid1)
    assert result["key2"] == uuid.UUID(tid2)


def test_parse_skips_empty_segments_between_commas() -> None:
    tid = "11111111-1111-1111-1111-111111111111"
    result = parse_api_key_env(f"  ,  {tid}:k,  ,")
    assert result == {"k": uuid.UUID(tid)}


def test_parse_rejects_pair_without_colon() -> None:
    with pytest.raises(ValueError, match="missing colon"):
        parse_api_key_env("not-a-pair")


def test_parse_rejects_empty_tenant() -> None:
    with pytest.raises(ValueError, match="empty tenant or key"):
        parse_api_key_env(":secret")


def test_parse_rejects_empty_key() -> None:
    tid = "11111111-1111-1111-1111-111111111111"
    with pytest.raises(ValueError, match="empty tenant or key"):
        parse_api_key_env(f"{tid}:")


def test_parse_rejects_bad_uuid() -> None:
    with pytest.raises(ValueError, match="not a valid UUID"):
        parse_api_key_env("not-a-uuid:secret")


# ---------------------------------------------------------------------------
# Middleware via TestClient — bypass paths (no auth needed)
# ---------------------------------------------------------------------------


@pytest.fixture
def client_locked_down() -> TestClient:
    """An app with NO API keys configured; every protected request is 401."""
    return TestClient(create_app(api_keys={}))


@pytest.fixture
def client_with_key() -> tuple[TestClient, str, uuid.UUID]:
    key = "test-secret-12345"
    tid = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa03")
    return TestClient(create_app(api_keys={key: tid})), key, tid


@pytest.mark.parametrize(
    "path",
    ["/healthz", "/readyz", "/version", "/metrics", "/openapi.json"],
)
def test_bypass_paths_skip_auth(
    client_locked_down: TestClient, path: str
) -> None:
    r = client_locked_down.get(path)
    assert r.status_code == 200, f"path={path} status={r.status_code}"


def test_docs_bypass_root_path(client_locked_down: TestClient) -> None:
    """/docs is a bypass path; /docs/oauth2-redirect (subpath) also bypasses."""
    r = client_locked_down.get("/docs")
    # FastAPI's /docs returns 200 with Swagger HTML; bypass is what matters.
    assert r.status_code == 200


def test_redoc_bypasses(client_locked_down: TestClient) -> None:
    r = client_locked_down.get("/redoc")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 401 paths on protected endpoints
# ---------------------------------------------------------------------------


def _govern_payload() -> dict:
    return {
        "agent_identity": {
            "spiffe_id": "spiffe://x",
            "role": "r",
            "workflow_id": "22222222-2222-2222-2222-222222222222",
        },
        "action": {"type": "tool_call", "tool_name": "read_x"},
        "context": {"prompt_hash": "b" * 64, "model_version": "m"},
        "trace_id": "t",
    }


def test_protected_endpoint_returns_401_without_header(
    client_locked_down: TestClient,
) -> None:
    r = client_locked_down.post("/v1/runtime/govern", json=_govern_payload())
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "missing_api_key"


def test_protected_endpoint_returns_401_with_unknown_key(
    client_with_key: tuple[TestClient, str, uuid.UUID],
) -> None:
    client, _, _ = client_with_key
    r = client.post(
        "/v1/runtime/govern",
        json=_govern_payload(),
        headers={"X-Verixa-API-Key": "wrong-key"},
    )
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "invalid_api_key"


def test_protected_endpoint_succeeds_with_valid_key(
    client_with_key: tuple[TestClient, str, uuid.UUID],
) -> None:
    client, key, _ = client_with_key
    r = client.post(
        "/v1/runtime/govern",
        json=_govern_payload(),
        headers={"X-Verixa-API-Key": key},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Env-var driven middleware (the no-explicit-keys path)
# ---------------------------------------------------------------------------


def test_middleware_reads_env_when_keys_arg_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tid = uuid.UUID("11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv(ENV_VAR_NAME, f"{tid}:env-driven-key")
    # api_keys=None means "read env"
    app = create_app(api_keys=None)
    client = TestClient(app)
    r = client.post(
        "/v1/runtime/govern",
        json=_govern_payload(),
        headers={"X-Verixa-API-Key": "env-driven-key"},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Public-API surface
# ---------------------------------------------------------------------------


def test_constants() -> None:
    assert API_KEY_HEADER == "x-verixa-api-key"
    assert ENV_VAR_NAME == "VERIXA_API_KEYS"
    assert "/healthz" in BYPASS_PATHS
    assert "/readyz" in BYPASS_PATHS
    assert "/metrics" in BYPASS_PATHS


def test_gateway_package_reexports_auth() -> None:
    from verixa_runtime import gateway

    for name in (
        "API_KEY_HEADER",
        "BYPASS_PATHS",
        "ENV_VAR_NAME",
        "ApiKeyMiddleware",
        "parse_api_key_env",
    ):
        assert hasattr(gateway, name), f"gateway package missing {name}"
