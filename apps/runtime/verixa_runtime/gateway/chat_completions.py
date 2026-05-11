"""POST /v1/chat/completions — OpenAI-compatible proxy to vLLM-on-ROCm.

Per docs/08_api_specification/API_SPECIFICATION.md A7 2.1, this endpoint accepts an
OpenAI ChatCompletions request and proxies it to the configured vLLM
endpoint (Phase 0: live MI300X droplet at http://165.245.133.120:8000).

Phase 0 surface:
  - Pass-through proxy: forwards the request body verbatim to upstream
  - Returns upstream response body verbatim
  - Captures latency_ms + emits a structured-log event (CP-6.4 wires
    the structured logger; for now we use stdlib logging)
  - Phase-0 audit emit happens AFTER response-body received (CP-12 wires
    full persistence; for now the endpoint just returns the body)

Phase 0 explicitly does NOT yet:
  - Stream responses (Phase 1; OpenAI streaming is SSE which needs
    middleware support)
  - Inspect response content for policy violations (CP-11 evidence
    validator)
  - Enforce per-tenant rate limits (CP-15)

Configuration:
  - Upstream URL via env var VERIXA_VLLM_BASE_URL
    (default http://165.245.133.120:8000 for the hackathon droplet)
  - Timeout 60 s default; longer than typical 8s p95 but conservative

Test discipline: the upstream HTTP call goes through a module-level
async function `_proxy_to_upstream` that tests can monkey-patch to
return a fixed response without hitting the network.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/v1", tags=["chat"])

DEFAULT_VLLM_BASE_URL = "http://165.245.133.120:8000"
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = 60.0


def _upstream_base_url() -> str:
    return os.environ.get("VERIXA_VLLM_BASE_URL", DEFAULT_VLLM_BASE_URL)


async def _proxy_to_upstream(
    base_url: str, body: dict[str, Any], timeout: float
) -> tuple[int, dict[str, Any]]:
    """Forward `body` to `base_url + /v1/chat/completions`.

    Returns ``(upstream_status_code, upstream_response_json)``. Tests
    monkey-patch this function to avoid network access.
    """
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=timeout) as client:
        upstream = await client.post(url, json=body)
    return upstream.status_code, upstream.json()


@router.post("/chat/completions")
async def chat_completions(request: Request) -> dict[str, Any]:
    """Proxy an OpenAI ChatCompletions request to the vLLM endpoint.

    Phase 0: pass-through. Audit-ledger persistence wires in CP-12.
    """
    started = time.monotonic()
    try:
        body = await request.json()
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail="invalid JSON body"
        ) from e
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail="request body must be a JSON object",
        )
    if "messages" not in body:
        raise HTTPException(
            status_code=400, detail="missing required field: messages"
        )

    base = _upstream_base_url()
    try:
        status_code, upstream_json = await _proxy_to_upstream(
            base, body, DEFAULT_UPSTREAM_TIMEOUT_SECONDS
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"upstream vLLM error: {type(e).__name__}",
        ) from e

    if status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                f"upstream returned {status_code}: "
                f"{upstream_json.get('error', upstream_json)}"
            ),
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    # Phase 0: attach a Verixa header-equivalent inside the body so
    # callers can correlate latency without inspecting headers (which
    # FastAPI strips by default on dict returns).
    upstream_json["_verixa"] = {
        "phase": "0",
        "latency_ms": elapsed_ms,
        "audit_id": None,  # CP-12 wires real audit_id
    }
    return upstream_json
