"""Structured JSON logging middleware for the Verixa Runtime Gateway.

Phase 0 implementation:
  - One JSON log line per request to a protected (non-bypass) path
  - Captured fields: timestamp, trace_id, tenant_id, path, method,
    status, latency_ms, api_key_hint (first 8 chars of the key, never
    the full key)
  - Uses stdlib `logging` with a JSON formatter; no structlog dep yet
    (CP-13 swaps in structlog with full Prometheus + OpenTelemetry
    instrumentation).
  - trace_id resolution order: header `X-Trace-Id` > generated UUID4

Bypass paths share the auth bypass list — health/version/metrics get a
brief log only at debug level (CP-13 wires that). Phase 0 simply skips
them.

Public API:
  - `StructuredLoggingMiddleware`   — ASGI middleware
  - `JsonLogFormatter`              — formatter for the verixa.runtime
                                      logger
  - `LOGGER_NAME`                   — "verixa.runtime"
  - `TRACE_ID_HEADER`               — "x-trace-id"
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Final

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from verixa_runtime.gateway.auth import _path_is_bypass

LOGGER_NAME: Final[str] = "verixa.runtime"
TRACE_ID_HEADER: Final[str] = "x-trace-id"


class JsonLogFormatter(logging.Formatter):
    """Renders a `logging.LogRecord` as a single-line JSON object.

    Fields written:
      - timestamp    UTC ISO-8601 with microseconds + "Z"
      - level        record.levelname
      - logger       record.name
      - message      record.getMessage()
      - <extras>     any keys passed via `logger.info(..., extra={...})`
    """

    _STANDARD_KEYS = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        ts = (
            datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
        out: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in self._STANDARD_KEYS or key.startswith("_"):
                continue
            out[key] = value
        return json.dumps(out, default=str, sort_keys=True)


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one JSON log line per protected request.

    Skips the same paths the API-key middleware bypasses.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._logger = logging.getLogger(LOGGER_NAME)

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        if _path_is_bypass(request.url.path):
            return await call_next(request)

        # trace_id from header if present, else mint a fresh UUID4
        trace_id = (
            request.headers.get(TRACE_ID_HEADER) or str(uuid.uuid4())
        )

        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            self._logger.exception(
                "runtime_request_error",
                extra={
                    "trace_id": trace_id,
                    "path": request.url.path,
                    "method": request.method,
                    "latency_ms": elapsed_ms,
                    "tenant_id": _state_tenant_id(request),
                    "api_key_hint": _state_api_key_hint(request),
                },
            )
            raise

        elapsed_ms = int((time.monotonic() - started) * 1000)
        self._logger.info(
            "runtime_request",
            extra={
                "trace_id": trace_id,
                "path": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "latency_ms": elapsed_ms,
                "tenant_id": _state_tenant_id(request),
                "api_key_hint": _state_api_key_hint(request),
            },
        )
        # Echo trace_id back so caller can correlate
        response.headers[TRACE_ID_HEADER] = trace_id
        return response


def _state_tenant_id(request: Request) -> str | None:
    tid = getattr(request.state, "tenant_id", None)
    return str(tid) if tid is not None else None


def _state_api_key_hint(request: Request) -> str | None:
    hint = getattr(request.state, "api_key_hint", None)
    return str(hint) if hint is not None else None
