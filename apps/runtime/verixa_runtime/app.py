"""Verixa Runtime Gateway — FastAPI application factory.

CP-2.5 ships only the operational endpoints:
  - GET /healthz      liveness probe (always 200 if process is up)
  - GET /readyz       readiness probe (200 if the gateway can serve)
  - GET /metrics      Prometheus exposition (text format 0.0.4)
  - GET /version      build + version info

CP-6+ will add the governance endpoints:
  - POST /v1/runtime/govern        primary governed-action endpoint
  - POST /v1/chat/completions      OpenAI-compatible proxy

The gateway is structured so adding routes later doesn't break the
operational endpoints or their tests.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from verixa_runtime import __version__

SERVICE_NAME = "verixa-runtime"

# Module-level start time used by readiness + uptime metric.
_START_TIME = time.monotonic()

# Pluggable readiness check. CP-3+ will replace this with real DB / Redis /
# OPA pings. Keeping it injectable so tests can simulate not-ready without
# patching the function itself.
ReadinessCheck = Callable[[], bool]


def _default_ready_check() -> bool:
    """Default readiness: process has been up for >= 0 seconds.

    Returning True is correct for CP-2.5 (no upstream deps wired yet).
    Tests inject a stub for the not-ready path so this default doesn't
    block 100% coverage.
    """
    return True


def create_app(ready_check: ReadinessCheck | None = None) -> FastAPI:
    """Build the FastAPI app. `ready_check` is dependency-injected for tests."""
    check = ready_check if ready_check is not None else _default_ready_check

    app = FastAPI(
        title="Verixa Runtime Gateway",
        version=__version__,
        description=(
            "Intercepts, verifies, governs, audits, replays, and creates "
            "evidence to demonstrate and support AI-driven actions before "
            "and after they affect the real world."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"status": "ok", "service": SERVICE_NAME}

    @app.get("/readyz")
    def readyz() -> Response:
        ready = check()
        body = {"ready": ready, "service": SERVICE_NAME}
        status = 200 if ready else 503
        return JSONResponse(content=body, status_code=status)

    @app.get("/version")
    def version() -> dict[str, Any]:
        return {
            "service": SERVICE_NAME,
            "version": __version__,
            "phase": "0",
            "build_id": os.environ.get("VERIXA_BUILD_ID", "dev"),
        }

    @app.get("/metrics")
    def metrics() -> Response:
        # Plain Prometheus exposition; structlog/full instrumentation in CP-13.
        uptime_seconds = time.monotonic() - _START_TIME
        body = (
            "# HELP verixa_runtime_up Whether the runtime is up (1 = up).\n"
            "# TYPE verixa_runtime_up gauge\n"
            f'verixa_runtime_up{{service="{SERVICE_NAME}"}} 1\n'
            "# HELP verixa_runtime_uptime_seconds Process uptime in seconds.\n"
            "# TYPE verixa_runtime_uptime_seconds gauge\n"
            f'verixa_runtime_uptime_seconds{{service="{SERVICE_NAME}"}} '
            f"{uptime_seconds:.3f}\n"
            "# HELP verixa_runtime_build_info Build info as labels.\n"
            "# TYPE verixa_runtime_build_info gauge\n"
            f'verixa_runtime_build_info{{service="{SERVICE_NAME}",'
            f'version="{__version__}"}} 1\n'
        )
        return PlainTextResponse(
            content=body,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


# Default app instance for `uvicorn verixa_runtime.app:app`
app = create_app()
