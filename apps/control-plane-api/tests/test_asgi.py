"""pytest suite for verixa_control_plane.asgi (CP-17).

Covers the production ASGI entry-point used by the Hugging Face
Spaces Dockerfile. The module's import runs an asyncio.run on
the demo seed, so importing it inside the test (via _build_seeded_app)
exercises the seed path end-to-end and confirms the app surface
is wired correctly.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from verixa_control_plane import asgi


def test_app_is_a_fastapi_instance() -> None:
    assert isinstance(asgi.app, FastAPI)


def test_seeded_app_responds_with_demo_workflow() -> None:
    """Import-time seed means the first /v1/control/workflows call
    against the already-built ``asgi.app`` returns the demo workflow
    without any further action."""
    client = TestClient(asgi.app)
    r = client.get("/v1/control/workflows")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["workflows"][0]["sector"] == "financial-services"


def test_build_seeded_app_is_idempotent_per_call() -> None:
    """Each call to _build_seeded_app yields a fresh FastAPI with a
    fresh seeded state -- IDs differ between calls but the seed
    structure is stable (1 workflow, 1 agent)."""
    a1 = asgi._build_seeded_app()
    a2 = asgi._build_seeded_app()
    assert isinstance(a1, FastAPI)
    assert isinstance(a2, FastAPI)
    assert a1 is not a2  # distinct instances
    c1 = TestClient(a1).get("/v1/control/workflows").json()
    c2 = TestClient(a2).get("/v1/control/workflows").json()
    # Same structure, different workflow_id.
    assert c1["total"] == c2["total"] == 1
    assert (
        c1["workflows"][0]["workflow_id"]
        != c2["workflows"][0]["workflow_id"]
    )


def test_asgi_module_exports_app() -> None:
    """``__all__`` keeps ``app`` as the only public name -- uvicorn
    imports it by attribute lookup, so the surface must stay stable."""
    assert asgi.__all__ == ["app"]
