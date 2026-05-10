"""Pydantic v2 envelopes for the Runtime Gateway.

Maps directly to docs/05_api/API_SPECIFICATION.md A7 2.1. Phase 0 implements
the canonical /v1/runtime/govern shapes (request + allow/deny/escalate
response variants). The envelope is intentionally additive-only on
non-required fields so CP-9 (decision router) can extend it without
breaking on-the-wire compatibility.

Design rules:
  - Strict mode: extra fields rejected. Tightening over time is a SemVer-
    minor break for the request side; we treat the surface as "additive
    on response, strict on request".
  - All UUIDs typed as `UUID` so FastAPI serialises canonically.
  - All bytes carried as hex strings on the wire (32-byte hashes -> 64
    hex chars; 64-byte signatures -> 128 hex chars). The Phase 0 envelope
    only exposes hashes (no signatures); CP-9 adds signatures for the
    audit-receipt subfield.
  - latency_ms is non-negative integer.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Decision(str, Enum):
    """The three possible governed-action outcomes."""

    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


class RiskClassification(str, Enum):
    """Risk band attached to a decision (computed by CP-9 risk engine)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyResult(str, Enum):
    """Per-policy evaluation outcome."""

    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"


# ---------------------------------------------------------------------------
# Request envelope
# ---------------------------------------------------------------------------


_HEX_64 = Annotated[
    str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
]


class AgentIdentity(BaseModel):
    """Caller agent's claimed identity (verified by mTLS / SPIFFE in Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    spiffe_id: str = Field(min_length=1, max_length=512)
    role: str = Field(min_length=1, max_length=128)
    workflow_id: uuid.UUID


class GovernAction(BaseModel):
    """The candidate action the agent wants to take."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call", "model_invocation", "data_access", "external_api"]
    tool_name: str | None = Field(default=None, max_length=256)
    arguments: dict[str, object] = Field(default_factory=dict)


class RetrievedDocument(BaseModel):
    """A single retrieved-context document (RAG / KB hit) in the action."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(min_length=1, max_length=256)
    hash: _HEX_64  # SHA-256 hex


class GovernContext(BaseModel):
    """Execution-time context the agent supplies for the action."""

    model_config = ConfigDict(extra="forbid")

    prompt_hash: _HEX_64  # SHA-256 hex of the prompt
    retrieved_documents: list[RetrievedDocument] = Field(default_factory=list)
    model_version: str = Field(min_length=1, max_length=128)
    reasoning_chain_summary: str | None = Field(default=None, max_length=8192)
    workflow_state: str | None = Field(default=None, max_length=128)


class GovernRequest(BaseModel):
    """`POST /v1/runtime/govern` request body."""

    model_config = ConfigDict(extra="forbid")

    agent_identity: AgentIdentity
    action: GovernAction
    context: GovernContext
    trace_id: str = Field(min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


class PolicyAppliedResult(BaseModel):
    """Per-policy result reported to the caller."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=256)
    result: PolicyResult


class GovernResponse(BaseModel):
    """Unified response shape covering allow / deny / escalate.

    The fields used per decision branch:
      - allow:    decision, audit_id, risk_score, risk_classification,
                  policies_applied, triad_invoked, latency_ms
      - deny:     decision, audit_id, reason, policy_id, policy_message,
                  risk_score, risk_classification, latency_ms,
                  remediation_suggestion
      - escalate: decision, audit_id, escalation_target, escalation_id,
                  risk_score, risk_classification, triad_invoked,
                  triad_consensus, estimated_review_time_minutes,
                  status_check_url, latency_ms

    Phase 0 returns a deterministic stub decision in CP-6.2; CP-9 wires
    the real risk engine + decision router.
    """

    model_config = ConfigDict(extra="forbid")

    decision: Decision
    audit_id: uuid.UUID
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_classification: RiskClassification
    latency_ms: int = Field(ge=0)

    # Allow / Escalate optional
    policies_applied: list[PolicyAppliedResult] = Field(default_factory=list)
    triad_invoked: bool = False

    # Deny optional
    reason: str | None = None
    policy_id: str | None = None
    policy_message: str | None = None
    remediation_suggestion: str | None = None

    # Escalate optional
    escalation_target: str | None = None
    escalation_id: uuid.UUID | None = None
    triad_consensus: str | None = None
    estimated_review_time_minutes: int | None = Field(default=None, ge=0)
    status_check_url: str | None = None

    @field_validator("policies_applied", mode="before")
    @classmethod
    def _coerce_none_to_empty(cls, v: object) -> object:
        """JSON null -> empty list (caller convenience)."""
        if v is None:
            return []
        return v
