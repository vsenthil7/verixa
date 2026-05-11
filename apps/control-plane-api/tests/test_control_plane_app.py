"""pytest suite for verixa_control_plane.app — operational endpoints.

Mirror of the runtime suite. 100% line + branch coverage.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from verixa_control_plane import __version__
from verixa_control_plane.app import SERVICE_NAME, app, create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_healthz_returns_200_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": SERVICE_NAME}


def test_readyz_default_returns_200(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"ready": True, "service": SERVICE_NAME}


def test_readyz_can_return_503_when_not_ready() -> None:
    not_ready_client = TestClient(create_app(ready_check=lambda: False))
    r = not_ready_client.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"ready": False, "service": SERVICE_NAME}


def test_version_payload_shape(client: TestClient) -> None:
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == SERVICE_NAME
    assert body["version"] == __version__
    assert body["phase"] == "0"
    assert "build_id" in body


def test_version_build_id_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERIXA_BUILD_ID", "xyz789")
    isolated_client = TestClient(create_app())
    r = isolated_client.get("/version")
    assert r.json()["build_id"] == "xyz789"


def test_metrics_returns_prometheus_text(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "verixa_control_plane_up" in body
    assert "verixa_control_plane_uptime_seconds" in body
    assert "verixa_control_plane_build_info" in body
    assert f'service="{SERVICE_NAME}"' in body


def test_metrics_uptime_is_non_negative(client: TestClient) -> None:
    body = client.get("/metrics").text
    uptime_line = next(
        line
        for line in body.splitlines()
        if line.startswith("verixa_control_plane_uptime_seconds{")
    )
    value = float(uptime_line.rsplit(" ", 1)[-1])
    assert value >= 0.0


def test_openapi_advertises_operational_endpoints(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["info"]["title"] == "Verixa Control Plane API"
    paths = spec["paths"]
    for endpoint in ("/healthz", "/readyz", "/version", "/metrics"):
        assert endpoint in paths, f"missing: {endpoint}"
