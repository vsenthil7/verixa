"""Verixa Control Plane API service.

The Control Plane is the operator-facing API: workflow registration, agent
management, audit-ledger query, replay request, dossier generation.

CP-14 sub-CPs:
  CP-14.1 -- envelope models (this commit's surface).
  CP-14.2 -- replay + dossier endpoints (read paths).
  CP-14.3 -- audit-log query endpoint.
  CP-14.4 -- workflow/agent/tool registration endpoints.
  CP-14.5 -- wire all routes into the FastAPI app + dependency
              injection for snapshotter/reconstructor.
"""

from verixa_control_plane.envelopes import (  # noqa: F401
    AgentRegisterRequest,
    AgentRegisterResponse,
    AuditEntry,
    AuditQueryResponse,
    DossierGenerateRequest,
    DossierGenerateResponse,
    DossierGetResponse,
    ErrorResponse,
    ReplayRequest,
    ReplayResponse,
    ToolRegisterRequest,
    ToolRegisterResponse,
    WorkflowListResponse,
    WorkflowRegisterRequest,
    WorkflowRegisterResponse,
    WorkflowSummary,
)

__version__ = "0.1.0"


__all__ = [
    "AgentRegisterRequest",
    "AgentRegisterResponse",
    "AuditEntry",
    "AuditQueryResponse",
    "DossierGenerateRequest",
    "DossierGenerateResponse",
    "DossierGetResponse",
    "ErrorResponse",
    "ReplayRequest",
    "ReplayResponse",
    "ToolRegisterRequest",
    "ToolRegisterResponse",
    "WorkflowListResponse",
    "WorkflowRegisterRequest",
    "WorkflowRegisterResponse",
    "WorkflowSummary",
    "__version__",
]
