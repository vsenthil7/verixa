"""Verixa Runtime Gateway — hot-path governance endpoints.

Two endpoints per docs/05_api/API_SPECIFICATION.md A7 2.1:

  - POST /v1/runtime/govern        — primary governed-action endpoint
  - POST /v1/chat/completions      — OpenAI-compatible proxy variant

Plus the support surface: API-key auth, structured JSON logs with
trace_id, Pydantic v2 envelopes for typed boundary validation.

CP-6 sub-CPs:
  CP-6.1 — envelope models (this commit)
  CP-6.2 — /v1/runtime/govern endpoint (Phase-0 stub pipeline)
  CP-6.3 — /v1/chat/completions OpenAI-compat proxy
  CP-6.4 — API-key auth + structured logging middleware

The full pipeline (policy -> risk -> triad -> emit-audit) lands across
CP-8/9/10. CP-6 wires the envelope shapes and the call points so the
endpoints are reachable end-to-end, with a simple deterministic stub
decision in CP-6.2 that becomes the real decision router in CP-9.
"""

from verixa_runtime.gateway.envelopes import (  # noqa: F401
    AgentIdentity,
    Decision,
    GovernAction,
    GovernContext,
    GovernRequest,
    GovernResponse,
    PolicyResult,
    RiskClassification,
)

__all__ = [
    "AgentIdentity",
    "Decision",
    "GovernAction",
    "GovernContext",
    "GovernRequest",
    "GovernResponse",
    "PolicyResult",
    "RiskClassification",
]
