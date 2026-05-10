"""Verixa Runtime Gateway — hot-path governance endpoints.

Two endpoints per docs/05_api/API_SPECIFICATION.md A7 2.1:

  - POST /v1/runtime/govern        — primary governed-action endpoint
  - POST /v1/chat/completions      — OpenAI-compatible proxy variant

Plus the support surface: API-key auth, structured JSON logs with
trace_id, Pydantic v2 envelopes for typed boundary validation.

CP-6 sub-CPs:
  CP-6.1 — envelope models
  CP-6.2 — /v1/runtime/govern endpoint (Phase-0 stub pipeline)
  CP-6.3 — /v1/chat/completions OpenAI-compat proxy
  CP-6.4 — API-key auth + structured logging middleware

CP-9.2 — endpoint dispatch swapped from ``decide_phase0`` (CP-6.2 stub,
retained for backward-compat) to ``decide_via_router`` (firewall +
CP-9.1 decision router). OPA + audit-emit + triad still pending
(CP-10, CP-12).
"""

from verixa_runtime.gateway.auth import (  # noqa: F401
    API_KEY_HEADER,
    BYPASS_PATHS,
    ENV_VAR_NAME,
    ApiKeyMiddleware,
    parse_api_key_env,
)
from verixa_runtime.gateway.chat_completions import (  # noqa: F401
    router as chat_router,
)
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
from verixa_runtime.gateway.govern import (  # noqa: F401
    decide_phase0,
    decide_via_router,
    decide_via_router_with_replay,
    decide_via_router_with_triad,
    pending_snapshot_tasks,
    router as govern_router,
)
from verixa_runtime.gateway.logging import (  # noqa: F401
    LOGGER_NAME,
    TRACE_ID_HEADER,
    JsonLogFormatter,
    StructuredLoggingMiddleware,
)

__all__ = [
    "API_KEY_HEADER",
    "AgentIdentity",
    "ApiKeyMiddleware",
    "BYPASS_PATHS",
    "Decision",
    "ENV_VAR_NAME",
    "GovernAction",
    "GovernContext",
    "GovernRequest",
    "GovernResponse",
    "JsonLogFormatter",
    "LOGGER_NAME",
    "PolicyResult",
    "RiskClassification",
    "StructuredLoggingMiddleware",
    "TRACE_ID_HEADER",
    "chat_router",
    "decide_phase0",
    "decide_via_router",
    "decide_via_router_with_replay",
    "decide_via_router_with_triad",
    "govern_router",
    "parse_api_key_env",
    "pending_snapshot_tasks",
]
