"""pytest suite for verixa_runtime.app — operational endpoints.

100% line + branch coverage discipline. The not-ready branch in /readyz is
exercised via dependency-injected ready_check callable.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from verixa_runtime import __version__
from verixa_runtime.app import SERVICE_NAME, app, create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------


def test_healthz_returns_200_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "service": SERVICE_NAME}


# ---------------------------------------------------------------------------
# /readyz — both branches
# ---------------------------------------------------------------------------


def test_readyz_default_returns_200(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ready": True, "service": SERVICE_NAME}


def test_readyz_can_return_503_when_not_ready() -> None:
    not_ready_app = create_app(ready_check=lambda: False)
    not_ready_client = TestClient(not_ready_app)
    r = not_ready_client.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body == {"ready": False, "service": SERVICE_NAME}


# ---------------------------------------------------------------------------
# /version
# ---------------------------------------------------------------------------


def test_version_payload_shape(client: TestClient) -> None:
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == SERVICE_NAME
    assert body["version"] == __version__
    assert body["phase"] == "0"
    assert "build_id" in body


def test_version_build_id_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERIXA_BUILD_ID", "abc123")
    isolated_app = create_app()
    isolated_client = TestClient(isolated_app)
    r = isolated_client.get("/version")
    assert r.status_code == 200
    assert r.json()["build_id"] == "abc123"


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------


def test_metrics_returns_prometheus_text(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "version=0.0.4" in r.headers["content-type"]
    body = r.text
    assert "verixa_runtime_up" in body
    assert "verixa_runtime_uptime_seconds" in body
    assert "verixa_runtime_build_info" in body
    assert f'service="{SERVICE_NAME}"' in body
    assert f'version="{__version__}"' in body


def test_metrics_uptime_is_non_negative(client: TestClient) -> None:
    r = client.get("/metrics")
    body = r.text
    # Find the uptime line and parse its numeric value
    uptime_line = next(
        line
        for line in body.splitlines()
        if line.startswith("verixa_runtime_uptime_seconds{")
    )
    value = float(uptime_line.rsplit(" ", 1)[-1])
    assert value >= 0.0


# ---------------------------------------------------------------------------
# OpenAPI / docs
# ---------------------------------------------------------------------------


def test_openapi_advertises_operational_endpoints(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["info"]["title"] == "Verixa Runtime Gateway"
    paths = spec["paths"]
    for endpoint in ("/healthz", "/readyz", "/version", "/metrics"):
        assert endpoint in paths, f"missing in OpenAPI: {endpoint}"
