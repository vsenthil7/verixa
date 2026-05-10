"""Verixa Control Plane API — FastAPI application factory.

CP-2.5 ships only the operational endpoints (parallel to the Runtime
Gateway). CP-14 will add the workflow / agent / audit / replay / dossier
routes per docs/05_api/API_SPECIFICATION.md §3.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from verixa_control_plane import __version__

SERVICE_NAME = "verixa-control-plane-api"

_START_TIME = time.monotonic()

ReadinessCheck = Callable[[], bool]


def _default_ready_check() -> bool:
    return True


def create_app(ready_check: ReadinessCheck | None = None) -> FastAPI:
    check = ready_check if ready_check is not None else _default_ready_check

    app = FastAPI(
        title="Verixa Control Plane API",
        version=__version__,
        description=(
            "Operator-facing API: workflow registration, agent management, "
            "audit-ledger query, replay request, dossier generation."
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
        uptime_seconds = time.monotonic() - _START_TIME
        body = (
            "# HELP verixa_control_plane_up Whether the control plane is up.\n"
            "# TYPE verixa_control_plane_up gauge\n"
            f'verixa_control_plane_up{{service="{SERVICE_NAME}"}} 1\n'
            "# HELP verixa_control_plane_uptime_seconds Process uptime.\n"
            "# TYPE verixa_control_plane_uptime_seconds gauge\n"
            f'verixa_control_plane_uptime_seconds{{service="{SERVICE_NAME}"}} '
            f"{uptime_seconds:.3f}\n"
            "# HELP verixa_control_plane_build_info Build info as labels.\n"
            "# TYPE verixa_control_plane_build_info gauge\n"
            f'verixa_control_plane_build_info{{service="{SERVICE_NAME}",'
            f'version="{__version__}"}} 1\n'
        )
        return PlainTextResponse(
            content=body,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


app = create_app()
