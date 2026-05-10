"""API-key authentication for the Verixa Runtime Gateway.

Phase 0 implementation:
  - Keys stored in env var VERIXA_API_KEYS as a comma-separated list of
    `tenant_id:api_key` pairs (e.g.
    `aaaa-...-aaaa:secret-key-1,bbbb-...-bbbb:secret-key-2`).
  - Caller sends `X-Verixa-API-Key: secret-key-1`; middleware looks up
    the matching tenant_id and attaches it to `request.state.tenant_id`.
  - Missing or unknown key on protected paths → 401 Unauthorized.
  - Operational paths (/healthz, /readyz, /version, /metrics, /docs,
    /redoc, /openapi.json, /) bypass auth.

Phase 1 will replace the env-var key store with a Postgres-backed
`verixa_tenancy.api_keys` table joined to verixa_tenancy.tenants. The
middleware contract — header name, 401 behaviour, request.state.tenant_id
attribute — will not change.

Public API:
  - `ApiKeyMiddleware`              — Starlette-style ASGI middleware
  - `parse_api_key_env`             — parses VERIXA_API_KEYS env value
  - `API_KEY_HEADER`                — header name constant
  - `BYPASS_PATHS`                  — paths that skip auth
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from typing import Final

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

API_KEY_HEADER: Final[str] = "x-verixa-api-key"
ENV_VAR_NAME: Final[str] = "VERIXA_API_KEYS"

# Paths that skip auth. Every path-prefix match is exact-or-startswith.
BYPASS_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/",
        "/healthz",
        "/readyz",
        "/version",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)


def parse_api_key_env(raw: str) -> dict[str, uuid.UUID]:
    """Parse `VERIXA_API_KEYS` env value into ``{api_key: tenant_id}``.

    Format: comma-separated `tenant_id:api_key` pairs. Whitespace
    tolerated. Empty input returns an empty mapping (auth always
    fails — useful for "lock down" mode in tests).

    Raises `ValueError` on malformed entries (no colon, bad UUID).
    """
    out: dict[str, uuid.UUID] = {}
    if not raw or not raw.strip():
        return out
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise ValueError(
                f"VERIXA_API_KEYS entry missing colon: {pair!r}"
            )
        tid_str, key = pair.split(":", 1)
        tid_str = tid_str.strip()
        key = key.strip()
        if not tid_str or not key:
            raise ValueError(
                f"VERIXA_API_KEYS entry has empty tenant or key: {pair!r}"
            )
        try:
            tid = uuid.UUID(tid_str)
        except ValueError as e:
            raise ValueError(
                f"VERIXA_API_KEYS tenant_id is not a valid UUID: {tid_str!r}"
            ) from e
        out[key] = tid
    return out


def _path_is_bypass(path: str) -> bool:
    """Return True if the path skips auth."""
    if path in BYPASS_PATHS:
        return True
    # docs subpaths: /docs/oauth2-redirect, /redoc/..., etc.
    return any(path.startswith(p + "/") for p in BYPASS_PATHS if p != "/")


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject protected requests without a valid `X-Verixa-API-Key` header.

    On success, attaches:
      - `request.state.tenant_id`   — `uuid.UUID` of the authenticated tenant
      - `request.state.api_key_hint` — first 8 chars of the key (for logs)
    """

    def __init__(
        self,
        app: ASGIApp,
        keys: dict[str, uuid.UUID] | None = None,
    ) -> None:
        super().__init__(app)
        # If keys is None, read from env at construction time (allows the
        # app factory to wire env-driven default; tests pass keys=...).
        if keys is None:
            keys = parse_api_key_env(os.environ.get(ENV_VAR_NAME, ""))
        self._keys = keys

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> JSONResponse:
        if _path_is_bypass(request.url.path):
            return await call_next(request)

        provided = request.headers.get(API_KEY_HEADER)
        if not provided:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "missing_api_key",
                    "detail": (
                        f"Header '{API_KEY_HEADER}' is required for "
                        "protected endpoints."
                    ),
                },
            )
        if provided not in self._keys:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "invalid_api_key",
                    "detail": "API key not recognised.",
                },
            )

        request.state.tenant_id = self._keys[provided]
        request.state.api_key_hint = provided[:8]
        return await call_next(request)
