"""Control Plane API envelope models (CP-14.1).

Pydantic v2 request/response shapes for every Control Plane endpoint.
Mirrors the runtime gateway's envelopes.py pattern: typed boundary
validation, ``extra='forbid'`` so unknown fields are rejected, no
behaviour in the models themselves.

Endpoints carved into four groups (mirrors the API spec §3):

  Registry
    - WorkflowRegisterRequest / WorkflowRegisterResponse
    - WorkflowListResponse + WorkflowSummary
    - AgentRegisterRequest / AgentRegisterResponse
    - ToolRegisterRequest / ToolRegisterResponse

  Audit
    - AuditQueryRequest (query params, not body)
    - AuditQueryResponse + AuditEntry

  Replay
    - ReplayRequest / ReplayResponse

  Dossier
    - DossierGenerateRequest / DossierGenerateResponse
    - DossierGetResponse (full SignedDossier inline)

All identifiers are UUID4. Timestamps are ISO-8601 strings on the
wire (Pydantic v2 serialises datetime that way by default with
``mode='json'``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


_strict = ConfigDict(extra="forbid", frozen=False)


# ---------------------------------------------------------------------------
# Registry envelopes
# ---------------------------------------------------------------------------


class WorkflowRegisterRequest(BaseModel):
    """Register a new workflow under the calling tenant."""

    model_config = _strict

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    sector: str = Field(
        default="generic",
        description="Industry tag, e.g. 'financial-services', 'healthcare'.",
        max_length=64,
    )
    risk_threshold_escalate: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description=(
            "Above this risk score, the workflow's decisions escalate "
            "to triad review."
        ),
    )


class WorkflowRegisterResponse(BaseModel):
    model_config = _strict

    workflow_id: uuid.UUID
    name: str
    sector: str
    created_at: datetime


class WorkflowSummary(BaseModel):
    """One row in WorkflowListResponse.workflows."""

    model_config = _strict

    workflow_id: uuid.UUID
    name: str
    sector: str
    risk_threshold_escalate: float
    agent_count: int = Field(ge=0)
    created_at: datetime


class WorkflowListResponse(BaseModel):
    model_config = _strict

    workflows: list[WorkflowSummary] = Field(default_factory=list)
    total: int = Field(ge=0)


class AgentRegisterRequest(BaseModel):
    """Register an agent (an operational entity acting under a workflow).

    ``spiffe_id`` is the agent's SPIFFE identity in dev mode (Phase-0
    bypasses SPIFFE verification; the field is recorded for forward
    compatibility).
    """

    model_config = _strict

    workflow_id: uuid.UUID
    spiffe_id: str = Field(..., min_length=1, max_length=512)
    role: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)


class AgentRegisterResponse(BaseModel):
    model_config = _strict

    agent_id: uuid.UUID
    workflow_id: uuid.UUID
    spiffe_id: str
    role: str
    created_at: datetime


class ToolRegisterRequest(BaseModel):
    """Register a tool the agent may invoke (subject to firewall)."""

    model_config = _strict

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    is_active: bool = Field(default=True)
    allowed_workflow_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description=(
            "Empty list means 'any workflow'. Non-empty restricts the "
            "tool to the listed workflows."
        ),
    )


class ToolRegisterResponse(BaseModel):
    model_config = _strict

    tool_id: uuid.UUID
    name: str
    is_active: bool
    allowed_workflow_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime


# ---------------------------------------------------------------------------
# Audit query envelopes
# ---------------------------------------------------------------------------


class AuditEntry(BaseModel):
    """One row in AuditQueryResponse.entries.

    The audit ledger row itself carries more (hash chain links,
    Ed25519 signatures); the AuditEntry surface returned to the
    Control Plane API caller is a redacted view useful for
    listing and filtering.
    """

    model_config = _strict

    audit_id: uuid.UUID
    workflow_id: uuid.UUID
    decision: str  # "allow" / "deny" / "escalate"
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_classification: str  # "low" / "medium" / "high" / "critical"
    triad_invoked: bool
    timestamp: datetime


class AuditQueryResponse(BaseModel):
    model_config = _strict

    entries: list[AuditEntry] = Field(default_factory=list)
    total: int = Field(ge=0)
    workflow_id: uuid.UUID
    from_timestamp: datetime
    to_timestamp: datetime


# ---------------------------------------------------------------------------
# Replay envelopes
# ---------------------------------------------------------------------------


class ReplayRequest(BaseModel):
    """Request a previously-snapshotted decision by audit_id."""

    model_config = _strict

    audit_id: uuid.UUID


class ReplayResponse(BaseModel):
    """Reconstructed decision context.

    The fields here mirror the ReplayBundle from CP-12.1 but use
    Pydantic types for HTTP serialisation. Nested dicts/lists are
    rendered as JSON objects.
    """

    model_config = _strict

    audit_id: uuid.UUID
    tenant_id: uuid.UUID
    decision: str
    risk_score: float
    request_envelope: dict[str, Any]
    retrieved_documents: list[dict[str, str]] = Field(default_factory=list)
    # Each: {"doc_id": ..., "content_sha256": ...}
    tool_io: list[dict[str, Any]] = Field(default_factory=list)
    policy_evaluations: list[dict[str, str]] = Field(default_factory=list)
    # Each: {"package": ..., "decision": ..., "reason": ...}
    triad_review: dict[str, Any] | None = None
    timestamp_unix_ns: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Dossier envelopes
# ---------------------------------------------------------------------------


class DossierGenerateRequest(BaseModel):
    """Generate a dossier for a previously-decided audit_id."""

    model_config = _strict

    audit_id: uuid.UUID
    action_summary: str = Field(
        default="",
        max_length=2000,
        description=(
            "Auditor-readable summary of the action the dossier covers. "
            "Empty defaults to a system-generated summary."
        ),
    )


class DossierGenerateResponse(BaseModel):
    """Returned from POST /v1/control/dossier.

    Carries enough to fetch the full signed JSON via the
    follow-up GET /v1/control/dossier/{id} call.
    """

    model_config = _strict

    dossier_id: uuid.UUID
    audit_id: uuid.UUID
    signing_key_id: str
    generated_at: datetime


class DossierGetResponse(BaseModel):
    """Returned from GET /v1/control/dossier/{id}.

    Carries the full SignedDossier inline so the caller can verify
    it offline without further round-trips.
    """

    model_config = _strict

    dossier_id: uuid.UUID
    audit_id: uuid.UUID
    manifest: dict[str, Any]
    signature_hex: str = Field(min_length=128, max_length=128)
    public_key_hex: str = Field(min_length=64, max_length=64)


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Standard error shape for 4xx/5xx responses."""

    model_config = _strict

    error: str  # short identifier, e.g. "audit_not_found"
    message: str  # human-readable detail
    audit_id: uuid.UUID | None = None  # populated when relevant
