"""Production ASGI entry-point for the Verixa Control Plane (CP-17).

Builds the FastAPI app with the financial-services demo data
pre-seeded so a first-time visitor sees populated workflows,
audit history, replay bundles, and a signed dossier without any
operator action.

Used by:
  - Hugging Face Spaces (Dockerfile CMD via uvicorn)
  - Local dev (``uvicorn verixa_control_plane.asgi:app --port 8001``)

Why the seed runs at import time:
  HF Spaces health-probes the container within seconds of start
  and we want /v1/control/workflows to return the seeded workflow
  on the first request, not empty.

Why the seed runs in a dedicated thread (NOT asyncio.run, NOT
``loop.run_until_complete`` on a freshly-created loop in the
calling thread):
  Uvicorn imports this module from inside a thread that already
  has a running asyncio loop. Two failure modes were caught by
  the Playwright E2E suite (CP-21):

    (a) asyncio.run(...) raises ``cannot be called from a running
        event loop``.
    (b) loop.run_until_complete(...) on a freshly-created loop in
        the same thread raises ``Cannot run the event loop while
        another loop is running``.

  Running the seed in a separate thread with its OWN event loop
  sidesteps both. The thread.join() makes the import-time seed
  synchronous from uvicorn's point of view -- by the time
  ``app = _build_seeded_app()`` returns, the seed is finished.

In Phase-1, the seed will move to a FastAPI ``lifespan`` startup
hook in a long-lived process backed by Postgres, and the in-memory
state will be replaced by real persistence.
"""

from __future__ import annotations

import asyncio
import threading

from verixa_control_plane.demo_seed import seed_financial_services_demo
from verixa_control_plane.routes import (
    ControlPlaneState,
    build_default_state,
    create_app_with_state,
)


def _run_seed_in_thread(state: ControlPlaneState) -> None:
    """Drive ``seed_financial_services_demo`` synchronously from a
    fresh thread with its own event loop.

    Sidesteps uvicorn's already-running loop in the calling thread.
    """
    exc: list[BaseException] = []

    def _target() -> None:
        try:
            asyncio.run(seed_financial_services_demo(state))
        except BaseException as e:  # noqa: BLE001 -- re-raise via main thread
            exc.append(e)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join()
    if exc:
        raise exc[0]


def _build_seeded_app():
    """Construct the FastAPI app with demo data pre-loaded.

    Returns the FastAPI instance.
    """
    state = build_default_state()
    _run_seed_in_thread(state)
    return create_app_with_state(state)


# Uvicorn imports `app` by attribute name. Built once at module
# import time, reused for every request.
app = _build_seeded_app()


__all__ = ["app"]
