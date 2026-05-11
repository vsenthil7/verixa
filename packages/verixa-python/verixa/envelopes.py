"""CP-61/CP-62 -- typed envelope dataclasses for SDK response parsing.

Closes the v0.4.0 roadmap promise from both SDK CHANGELOGs: customers
can opt into typed return values instead of plain ``dict[str, Any]``.

Design notes:

  - Lightweight: ``@dataclass(frozen=True, slots=True)`` with no
    runtime dependency on Pydantic (customers who use Pydantic v2
    elsewhere can wrap our dicts themselves).
  - Opt-in: existing SDK methods still return ``dict[str, Any]``;
    new helper ``.from_dict`` classmethods take a response dict and
    return the typed object. The next SDK MINOR release (v0.2.0)
    will add ``register(..., return_typed=True)`` overloads; v1.0.0
    will flip the default.
  - Pinned to wire format: every field name + type here MUST match
    what ``apps/control-plane-api/verixa_control_plane/envelopes.py``
    emits on the wire. CP-62 corrected the Phase-0 CP-61 mismatch
    where WorkflowRegisterResponse had ``description + owner_tenant_id``
    fields the server does not emit (it emits ``sector``); the
    correction is contract-driven.
  - Defensive: each ``from_dict`` raises ``InvalidEnvelopeError``
    with a ``field {name}: ...`` prefix so a server returning an
    unexpected shape gives a debuggable error rather than KeyError.
  - Tolerant of EXTRA fields: server-side may add new optional fields
    (forward-compat); the parser ignores them. MISSING required
    fields are a hard error.
  - Strict invariants: naive datetimes rejected (Verixa requires
    TZ-aware everywhere); bool-as-int rejected (so True/False
    cannot be silently coerced into 1/0 totals); UUID-strings
    parsed but UUID-objects accepted as-is.

Subset shipped:

  CP-61 (workflow + audit core):
    - WorkflowRegisterResponse
    - WorkflowSummary + WorkflowListResponse
    - AuditEntry + AuditQueryResponse

  CP-62 (registry: agent + tool):
    - AgentRegisterResponse
    - ToolRegisterResponse

  CP-63 (replay + dossier):
    - ReplayResponse
    - DossierGenerateResponse + DossierGetResponse

The remaining envelopes (Webhook subscription + delivery summaries)
follow in subsequent commits as the type signatures land.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class InvalidEnvelopeError(ValueError):
    """A server response did not match the documented envelope shape.

    Use this to signal a hard parser failure (vs a network/HTTP error
    which is signalled by VerixaHttpError / VerixaConnectionError).
    Subclasses ValueError for backwards-compat with code catching that.
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require(d: dict[str, Any], key: str, name: str) -> Any:
    """Get d[key] or raise InvalidEnvelopeError(field=name)."""
    if key not in d:
        raise InvalidEnvelopeError(f"field {name}: missing from response")
    return d[key]


def _as_uuid(value: Any, name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if not isinstance(value, str):
        raise InvalidEnvelopeError(
            f"field {name}: expected uuid string, got {type(value).__name__}"
        )
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as e:
        raise InvalidEnvelopeError(
            f"field {name}: {value!r} is not a valid UUID"
        ) from e


def _as_uuid_list(value: Any, name: str) -> tuple[uuid.UUID, ...]:
    """Parse a list-of-uuids into an immutable tuple."""
    if not isinstance(value, list):
        raise InvalidEnvelopeError(
            f"field {name}: expected list of uuids, got {type(value).__name__}"
        )
    return tuple(_as_uuid(v, f"{name}[{i}]") for i, v in enumerate(value))


def _as_datetime(value: Any, name: str) -> datetime:
    """Parse an ISO-8601 timestamp (with TZ) into datetime.

    The server emits ISO-8601 with a Z suffix or explicit offset; we
    accept both. We do NOT accept naive timestamps -- the server-side
    audit ledger requires every entry have a TZ, and we propagate that
    invariant here so customers cannot silently drop TZ info."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise InvalidEnvelopeError(
                f"field {name}: datetime is naive (no tzinfo); "
                f"Verixa requires TZ-aware timestamps"
            )
        return value
    if not isinstance(value, str):
        raise InvalidEnvelopeError(
            f"field {name}: expected ISO-8601 string, got {type(value).__name__}"
        )
    try:
        # Python 3.11+ accepts 'Z' in fromisoformat
        parsed = datetime.fromisoformat(value)
    except ValueError as e:
        raise InvalidEnvelopeError(
            f"field {name}: {value!r} is not a valid ISO-8601 timestamp"
        ) from e
    if parsed.tzinfo is None:
        raise InvalidEnvelopeError(
            f"field {name}: {value!r} is naive (no tzinfo); "
            f"Verixa requires TZ-aware timestamps"
        )
    return parsed


def _as_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise InvalidEnvelopeError(
            f"field {name}: expected string, got {type(value).__name__}"
        )
    return value


def _as_int(value: Any, name: str) -> int:
    # bool is an int subclass in Python; reject explicitly to avoid
    # silently coercing True/False into 1/0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidEnvelopeError(
            f"field {name}: expected int, got {type(value).__name__}"
        )
    return value


def _as_float(value: Any, name: str) -> float:
    # bool is int subclass + int is float-compatible; accept int as
    # float (server may serialise 0.5 -> 0.5 but 0.0 -> 0). Reject bool.
    if isinstance(value, bool):
        raise InvalidEnvelopeError(
            f"field {name}: expected number, got bool"
        )
    if not isinstance(value, int | float):
        raise InvalidEnvelopeError(
            f"field {name}: expected number, got {type(value).__name__}"
        )
    return float(value)


def _as_bool(value: Any, name: str) -> bool:
    """Strict bool; reject int 0/1 since wire format uses true/false."""
    if not isinstance(value, bool):
        raise InvalidEnvelopeError(
            f"field {name}: expected bool, got {type(value).__name__}"
        )
    return value


def _as_dict(value: Any, name: str) -> dict[str, Any]:
    """Strict dict; rejects None, list, primitives.

    Used for nested envelope dicts that the SDK passes through opaquely
    (the customer can drill into them or wrap with their own model).
    """
    if not isinstance(value, dict):
        raise InvalidEnvelopeError(
            f"field {name}: expected dict, got {type(value).__name__}"
        )
    return value


def _as_optional_dict(value: Any, name: str) -> dict[str, Any] | None:
    """Like _as_dict but accepts None (for optional nested envelopes)."""
    if value is None:
        return None
    return _as_dict(value, name)


def _as_list_of_dict(value: Any, name: str) -> tuple[dict[str, Any], ...]:
    """Parse a list-of-dicts into an immutable tuple-of-dicts.

    The inner dicts pass through unparsed (each is opaque to the SDK
    surface; e.g. retrieved_documents is a list of {doc_id, content_sha256}
    items but ReplayResponse exposes them as plain dicts).
    """
    if not isinstance(value, list):
        raise InvalidEnvelopeError(
            f"field {name}: expected list of dicts, got {type(value).__name__}"
        )
    parsed: list[dict[str, Any]] = []
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            raise InvalidEnvelopeError(
                f"field {name}[{i}]: expected dict, "
                f"got {type(item).__name__}"
            )
        parsed.append(item)
    return tuple(parsed)


# ---------------------------------------------------------------------------
# Workflow envelopes (CP-61)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkflowRegisterResponse:
    """Server response to ``POST /v1/control/workflows``.

    Matches apps/control-plane-api/verixa_control_plane/envelopes.py
    WorkflowRegisterResponse exactly: workflow_id + name + sector +
    created_at. The Phase-0 CP-61 mismatch (description +
    owner_tenant_id fields the server does not emit) is corrected here.
    """

    workflow_id: uuid.UUID
    name: str
    sector: str
    created_at: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowRegisterResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for WorkflowRegisterResponse, "
                f"got {type(data).__name__}"
            )
        return cls(
            workflow_id=_as_uuid(
                _require(data, "workflow_id", "workflow_id"), "workflow_id"
            ),
            name=_as_str(_require(data, "name", "name"), "name"),
            sector=_as_str(_require(data, "sector", "sector"), "sector"),
            created_at=_as_datetime(
                _require(data, "created_at", "created_at"), "created_at"
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkflowSummary:
    """One workflow entry in a list response.

    Matches server-side WorkflowSummary: workflow_id + name + sector +
    risk_threshold_escalate + agent_count + created_at.
    """

    workflow_id: uuid.UUID
    name: str
    sector: str
    risk_threshold_escalate: float
    agent_count: int
    created_at: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowSummary:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for WorkflowSummary, got {type(data).__name__}"
            )
        return cls(
            workflow_id=_as_uuid(
                _require(data, "workflow_id", "workflow_id"), "workflow_id"
            ),
            name=_as_str(_require(data, "name", "name"), "name"),
            sector=_as_str(_require(data, "sector", "sector"), "sector"),
            risk_threshold_escalate=_as_float(
                _require(
                    data,
                    "risk_threshold_escalate",
                    "risk_threshold_escalate",
                ),
                "risk_threshold_escalate",
            ),
            agent_count=_as_int(
                _require(data, "agent_count", "agent_count"), "agent_count"
            ),
            created_at=_as_datetime(
                _require(data, "created_at", "created_at"), "created_at"
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkflowListResponse:
    """Server response to ``GET /v1/control/workflows``."""

    workflows: tuple[WorkflowSummary, ...]
    total: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowListResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for WorkflowListResponse, "
                f"got {type(data).__name__}"
            )
        items = _require(data, "workflows", "workflows")
        if not isinstance(items, list):
            raise InvalidEnvelopeError(
                f"field workflows: expected list, got {type(items).__name__}"
            )
        parsed = tuple(WorkflowSummary.from_dict(item) for item in items)
        return cls(
            workflows=parsed,
            total=_as_int(_require(data, "total", "total"), "total"),
        )


# ---------------------------------------------------------------------------
# Audit envelopes (CP-61)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One entry from the audit ledger as exposed by the Control Plane API.

    Matches the server's AuditEntry redacted view: audit_id +
    workflow_id + decision (allow/deny/escalate) + risk_score [0,1] +
    risk_classification (low/medium/high/critical) + triad_invoked +
    timestamp. Not the full ledger row (which carries hash chain links
    + Ed25519 signatures); that is the ReplayResponse.
    """

    audit_id: uuid.UUID
    workflow_id: uuid.UUID
    decision: str
    risk_score: float
    risk_classification: str
    triad_invoked: bool
    timestamp: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for AuditEntry, got {type(data).__name__}"
            )
        return cls(
            audit_id=_as_uuid(
                _require(data, "audit_id", "audit_id"), "audit_id"
            ),
            workflow_id=_as_uuid(
                _require(data, "workflow_id", "workflow_id"), "workflow_id"
            ),
            decision=_as_str(
                _require(data, "decision", "decision"), "decision"
            ),
            risk_score=_as_float(
                _require(data, "risk_score", "risk_score"), "risk_score"
            ),
            risk_classification=_as_str(
                _require(
                    data, "risk_classification", "risk_classification"
                ),
                "risk_classification",
            ),
            triad_invoked=_as_bool(
                _require(data, "triad_invoked", "triad_invoked"),
                "triad_invoked",
            ),
            timestamp=_as_datetime(
                _require(data, "timestamp", "timestamp"), "timestamp"
            ),
        )


@dataclass(frozen=True, slots=True)
class AuditQueryResponse:
    """Server response to ``GET /v1/control/audit``."""

    entries: tuple[AuditEntry, ...]
    total: int
    workflow_id: uuid.UUID
    from_timestamp: datetime
    to_timestamp: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditQueryResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for AuditQueryResponse, "
                f"got {type(data).__name__}"
            )
        items = _require(data, "entries", "entries")
        if not isinstance(items, list):
            raise InvalidEnvelopeError(
                f"field entries: expected list, got {type(items).__name__}"
            )
        parsed = tuple(AuditEntry.from_dict(item) for item in items)
        return cls(
            entries=parsed,
            total=_as_int(_require(data, "total", "total"), "total"),
            workflow_id=_as_uuid(
                _require(data, "workflow_id", "workflow_id"), "workflow_id"
            ),
            from_timestamp=_as_datetime(
                _require(data, "from_timestamp", "from_timestamp"),
                "from_timestamp",
            ),
            to_timestamp=_as_datetime(
                _require(data, "to_timestamp", "to_timestamp"),
                "to_timestamp",
            ),
        )


# ---------------------------------------------------------------------------
# Registry envelopes (CP-62 -- agent + tool)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentRegisterResponse:
    """Server response to ``POST /v1/control/agents``.

    Matches server-side AgentRegisterResponse: agent_id + workflow_id +
    spiffe_id + role + created_at. The agent is an operational entity
    acting under the workflow; spiffe_id is the SPIFFE identity
    (Phase-0 bypasses SPIFFE verification; the field is recorded for
    forward compatibility with the CP-53 mTLS Protocol surface).
    """

    agent_id: uuid.UUID
    workflow_id: uuid.UUID
    spiffe_id: str
    role: str
    created_at: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentRegisterResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for AgentRegisterResponse, "
                f"got {type(data).__name__}"
            )
        return cls(
            agent_id=_as_uuid(
                _require(data, "agent_id", "agent_id"), "agent_id"
            ),
            workflow_id=_as_uuid(
                _require(data, "workflow_id", "workflow_id"), "workflow_id"
            ),
            spiffe_id=_as_str(
                _require(data, "spiffe_id", "spiffe_id"), "spiffe_id"
            ),
            role=_as_str(_require(data, "role", "role"), "role"),
            created_at=_as_datetime(
                _require(data, "created_at", "created_at"), "created_at"
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolRegisterResponse:
    """Server response to ``POST /v1/control/tools``.

    Matches server-side ToolRegisterResponse: tool_id + name +
    is_active + allowed_workflow_ids (empty list = any workflow,
    non-empty = restricted) + created_at. The tool is something the
    agent may invoke (subject to firewall + per-tenant ACL).

    allowed_workflow_ids is returned as a tuple (immutable) so
    customers cannot mutate the parsed result.
    """

    tool_id: uuid.UUID
    name: str
    is_active: bool
    allowed_workflow_ids: tuple[uuid.UUID, ...]
    created_at: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolRegisterResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for ToolRegisterResponse, "
                f"got {type(data).__name__}"
            )
        return cls(
            tool_id=_as_uuid(
                _require(data, "tool_id", "tool_id"), "tool_id"
            ),
            name=_as_str(_require(data, "name", "name"), "name"),
            is_active=_as_bool(
                _require(data, "is_active", "is_active"), "is_active"
            ),
            allowed_workflow_ids=_as_uuid_list(
                _require(
                    data,
                    "allowed_workflow_ids",
                    "allowed_workflow_ids",
                ),
                "allowed_workflow_ids",
            ),
            created_at=_as_datetime(
                _require(data, "created_at", "created_at"), "created_at"
            ),
        )


# ---------------------------------------------------------------------------
# Replay envelopes (CP-63)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReplayResponse:
    """Server response to ``GET /v1/control/replay``.

    Reconstructed decision context for an audit_id. Mirrors the
    server-side ReplayResponse: full request envelope + retrieved
    documents + tool I/O + policy evaluations + optional triad review +
    timestamp.

    Nested dicts pass through opaquely (request_envelope is the
    original decision payload; retrieved_documents are
    {doc_id, content_sha256} pairs; tool_io captures every tool call
    request+response; policy_evaluations is one entry per Rego
    package evaluated). Customers can drill into them or wrap with
    their own model. The collections are tuples (immutable).

    triad_review is None when the decision did NOT go through triad
    review (i.e. AuditEntry.triad_invoked was False).
    """

    audit_id: uuid.UUID
    tenant_id: uuid.UUID
    decision: str
    risk_score: float
    request_envelope: dict[str, Any]
    retrieved_documents: tuple[dict[str, Any], ...]
    tool_io: tuple[dict[str, Any], ...]
    policy_evaluations: tuple[dict[str, Any], ...]
    triad_review: dict[str, Any] | None
    timestamp_unix_ns: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReplayResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for ReplayResponse, "
                f"got {type(data).__name__}"
            )
        return cls(
            audit_id=_as_uuid(
                _require(data, "audit_id", "audit_id"), "audit_id"
            ),
            tenant_id=_as_uuid(
                _require(data, "tenant_id", "tenant_id"), "tenant_id"
            ),
            decision=_as_str(
                _require(data, "decision", "decision"), "decision"
            ),
            risk_score=_as_float(
                _require(data, "risk_score", "risk_score"), "risk_score"
            ),
            request_envelope=_as_dict(
                _require(data, "request_envelope", "request_envelope"),
                "request_envelope",
            ),
            retrieved_documents=_as_list_of_dict(
                _require(
                    data,
                    "retrieved_documents",
                    "retrieved_documents",
                ),
                "retrieved_documents",
            ),
            tool_io=_as_list_of_dict(
                _require(data, "tool_io", "tool_io"), "tool_io"
            ),
            policy_evaluations=_as_list_of_dict(
                _require(
                    data, "policy_evaluations", "policy_evaluations"
                ),
                "policy_evaluations",
            ),
            triad_review=_as_optional_dict(
                data.get("triad_review"), "triad_review"
            ),
            timestamp_unix_ns=_as_int(
                _require(data, "timestamp_unix_ns", "timestamp_unix_ns"),
                "timestamp_unix_ns",
            ),
        )


# ---------------------------------------------------------------------------
# Dossier envelopes (CP-63)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DossierGenerateResponse:
    """Server response to ``POST /v1/control/dossier``.

    Carries enough to fetch the full signed JSON via the follow-up
    GET /v1/control/dossier/{id} call.
    """

    dossier_id: uuid.UUID
    audit_id: uuid.UUID
    signing_key_id: str
    generated_at: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DossierGenerateResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for DossierGenerateResponse, "
                f"got {type(data).__name__}"
            )
        return cls(
            dossier_id=_as_uuid(
                _require(data, "dossier_id", "dossier_id"), "dossier_id"
            ),
            audit_id=_as_uuid(
                _require(data, "audit_id", "audit_id"), "audit_id"
            ),
            signing_key_id=_as_str(
                _require(data, "signing_key_id", "signing_key_id"),
                "signing_key_id",
            ),
            generated_at=_as_datetime(
                _require(data, "generated_at", "generated_at"),
                "generated_at",
            ),
        )


@dataclass(frozen=True, slots=True)
class DossierGetResponse:
    """Server response to ``GET /v1/control/dossier/{id}``.

    Carries the full SignedDossier inline so the caller can verify it
    offline without further round-trips. signature_hex is 128 hex chars
    (Ed25519 sig = 64 bytes = 128 hex); public_key_hex is 64 hex chars
    (Ed25519 public key = 32 bytes = 64 hex). The manifest dict is
    opaque to the SDK -- the caller verifies it via the verixa_runtime
    crypto primitives.
    """

    dossier_id: uuid.UUID
    audit_id: uuid.UUID
    manifest: dict[str, Any]
    signature_hex: str
    public_key_hex: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DossierGetResponse:
        if not isinstance(data, dict):
            raise InvalidEnvelopeError(
                f"expected dict for DossierGetResponse, "
                f"got {type(data).__name__}"
            )
        sig = _as_str(
            _require(data, "signature_hex", "signature_hex"),
            "signature_hex",
        )
        if len(sig) != 128:
            raise InvalidEnvelopeError(
                f"field signature_hex: expected 128 hex chars, "
                f"got {len(sig)}"
            )
        pub = _as_str(
            _require(data, "public_key_hex", "public_key_hex"),
            "public_key_hex",
        )
        if len(pub) != 64:
            raise InvalidEnvelopeError(
                f"field public_key_hex: expected 64 hex chars, "
                f"got {len(pub)}"
            )
        return cls(
            dossier_id=_as_uuid(
                _require(data, "dossier_id", "dossier_id"), "dossier_id"
            ),
            audit_id=_as_uuid(
                _require(data, "audit_id", "audit_id"), "audit_id"
            ),
            manifest=_as_dict(
                _require(data, "manifest", "manifest"), "manifest"
            ),
            signature_hex=sig,
            public_key_hex=pub,
        )


__all__ = [
    "AgentRegisterResponse",
    "AuditEntry",
    "AuditQueryResponse",
    "DossierGenerateResponse",
    "DossierGetResponse",
    "InvalidEnvelopeError",
    "ReplayResponse",
    "ToolRegisterResponse",
    "WorkflowListResponse",
    "WorkflowRegisterResponse",
    "WorkflowSummary",
]
