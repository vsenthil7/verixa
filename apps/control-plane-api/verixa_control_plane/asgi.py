"""Production ASGI entry-point for the Verixa Control Plane (CP-17).

Builds the FastAPI app with the financial-services demo data
pre-seeded so a first-time visitor sees populated workflows,
audit history, replay bundles, and a signed dossier without any
operator action.

Used by:
  - Hugging Face Spaces (Dockerfile CMD via uvicorn)
  - Local dev (``uvicorn verixa_control_plane.asgi:app --port 8001``)

The seed runs synchronously inside ``asyncio.run`` at module load
time. This is intentional: HF Spaces health-probes the container
within seconds of start, and we want the first /v1/control/workflows
request to return the seeded workflow rather than empty.

In Phase-1, the seed will move to a startup hook in a long-lived
process backed by Postgres, and the in-memory state will be
replaced by real persistence.
"""

from __future__ import annotations

import asyncio

from verixa_control_plane.demo_seed import seed_financial_services_demo
from verixa_control_plane.routes import (
    build_default_state,
    create_app_with_state,
)


def _build_seeded_app():
    """Construct the FastAPI app with demo data pre-loaded.

    Returns the FastAPI instance. Side effect: the
    DemoSeedResult.workflow_id / audit_ids / dossier_id are
    available on app.state.cp via the ControlPlaneState fields,
    so demo links remain stable across container restarts (each
    restart picks fresh UUIDs but the seed structure is the same).
    """
    state = build_default_state()
    asyncio.run(seed_financial_services_demo(state))
    return create_app_with_state(state)


# Uvicorn imports `app` by attribute name. Built once at module
# import time, reused for every request.
app = _build_seeded_app()


__all__ = ["app"]
