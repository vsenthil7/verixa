"""Replay bundle types + canonical serialisation (CP-12.1).

A ReplayBundle captures the full decision context for a single
governed action. It is the unit of replay -- everything a third
party (auditor, regulator, internal reviewer) needs to reconstruct
"what the system saw and why it decided what it did" lives in here.

Phase-0 fields (mirrors docs/09_data_model/DATA_MODEL.md replay
schema):

  - schema_version          -- monotonic int; bumped when fields
                               change non-backward-compatibly
  - audit_id                -- UUID4 minted by the gateway; the
                               primary key tying this bundle to the
                               audit ledger row
  - tenant_id               -- UUID4; per-tenant isolation
  - decision                -- "allow" / "deny" / "escalate"
  - risk_score              -- float 0..1
  - request_envelope        -- the original GovernRequest as a dict
                               (Pydantic v2 model_dump output)
  - retrieved_documents     -- list of {doc_id, content_sha256} pairs
                               (NOT full content -- that lives in the
                               document store; we record fingerprints
                               so a replay can verify the docs the
                               agent saw are the docs in the store
                               today)
  - tool_io                 -- list of {call, response} pairs that
                               led up to the governed action
  - policy_evaluations      -- list of PolicyEvaluationRecord
  - triad_review            -- optional TriadReviewRecord
  - timestamp_unix_ns       -- int nanoseconds since epoch for
                               deterministic ordering

The bundle is canonically serialised to JSON for hashing and for the
AES-256-GCM ciphertext payload. Determinism is required: every byte
must be reproducible from the same input, otherwise the
content-addressable key (SHA-256 of the encrypted bytes) wouldn't be
stable and replay verification would fail.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Final


# Bumped when the bundle schema changes in a non-backward-compatible
# way. Reconstructor refuses to deserialise unknown versions so a
# downgrade can't silently misinterpret a newer bundle.
BUNDLE_SCHEMA_VERSION: Final[int] = 1


@dataclass(frozen=True, slots=True)
class PolicyEvaluationRecord:
    """One OPA policy evaluation result, captured at decision time."""

    package: str
    decision: str  # "pass" / "fail" / "abstain"
    reason: str

    def __post_init__(self) -> None:
        if not self.package:
            raise ValueError("package must be non-empty")
        if self.decision not in ("pass", "fail", "abstain"):
            raise ValueError(
                f"decision must be pass/fail/abstain; got {self.decision!r}"
            )


@dataclass(frozen=True, slots=True)
class TriadReviewRecord:
    """Triad outcome captured at decision time.

    Mirrors verixa_runtime.triad.protocol.ConsensusOutcome but
    flattened for serialisation and decoupled from the triad module's
    enum types (replay is stable across schema versions; triad enums
    may evolve).
    """

    consensus_kind: str  # "unanimous" / "majority" / "split" / "integrity_failure"
    agreed_decision: str | None  # "allow" / "deny" / "escalate" / None
    verdicts: tuple[
        tuple[str, str, float, str], ...
    ] = field(default_factory=tuple)
    # Each verdict tuple: (reviewer_id, decision, confidence, reasoning)
    commitments: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    # Each commitment tuple: (reviewer_id, sha256_hex)

    def __post_init__(self) -> None:
        if self.consensus_kind not in (
            "unanimous", "majority", "split", "integrity_failure"
        ):
            raise ValueError(
                f"consensus_kind must be one of "
                f"unanimous/majority/split/integrity_failure; "
                f"got {self.consensus_kind!r}"
            )
        if self.agreed_decision is not None and self.agreed_decision not in (
            "allow", "deny", "escalate"
        ):
            raise ValueError(
                f"agreed_decision must be allow/deny/escalate or None; "
                f"got {self.agreed_decision!r}"
            )


@dataclass(frozen=True, slots=True)
class ReplayBundle:
    """Complete decision context for one governed action."""

    audit_id: uuid.UUID
    tenant_id: uuid.UUID
    decision: str  # "allow" / "deny" / "escalate"
    risk_score: float
    request_envelope: dict[str, Any]
    retrieved_documents: tuple[
        tuple[str, str], ...
    ] = field(default_factory=tuple)
    # Each pair: (doc_id, content_sha256_hex)
    tool_io: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    policy_evaluations: tuple[
        PolicyEvaluationRecord, ...
    ] = field(default_factory=tuple)
    triad_review: TriadReviewRecord | None = None
    timestamp_unix_ns: int = 0
    schema_version: int = BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.decision not in ("allow", "deny", "escalate"):
            raise ValueError(
                f"decision must be allow/deny/escalate; got {self.decision!r}"
            )
        if not 0.0 <= self.risk_score <= 1.0:
            raise ValueError(
                f"risk_score must be in [0.0, 1.0]; got {self.risk_score!r}"
            )
        if self.timestamp_unix_ns < 0:
            raise ValueError(
                f"timestamp_unix_ns must be non-negative; "
                f"got {self.timestamp_unix_ns!r}"
            )
        if self.schema_version != BUNDLE_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {BUNDLE_SCHEMA_VERSION}; "
                f"got {self.schema_version!r}"
            )
        for d in self.retrieved_documents:
            if (
                not isinstance(d, tuple)
                or len(d) != 2
                or not isinstance(d[0], str)
                or not isinstance(d[1], str)
            ):
                raise ValueError(
                    "retrieved_documents entries must be (doc_id, "
                    "content_sha256_hex) string pairs"
                )
            # CP-30 Phase-1 gap closure (commit 2026-05-11 11:54 UK):
            # empty doc_id or empty hash slipped past the earlier
            # tuple-shape check. Now rejected explicitly. The xfail
            # marker in test_size_limits.py flips to GREEN.
            if not d[0]:
                raise ValueError(
                    "retrieved_documents doc_id must be non-empty"
                )
            if not d[1]:
                raise ValueError(
                    "retrieved_documents content_sha256_hex must be "
                    "non-empty"
                )


# ---------------------------------------------------------------------------
# Canonical serialisation
# ---------------------------------------------------------------------------


def canonicalise_bundle(bundle: ReplayBundle) -> bytes:
    """Deterministic JSON-bytes serialisation.

    Sorted keys + minimal separators so the byte output is stable
    across Python versions and dict-insertion orders. The result is
    what AES-GCM encrypts and what the content-addressable key
    (SHA-256) is computed over.

    Returns UTF-8 encoded bytes.
    """
    payload = {
        "schema_version": bundle.schema_version,
        "audit_id": str(bundle.audit_id),
        "tenant_id": str(bundle.tenant_id),
        "decision": bundle.decision,
        "risk_score": bundle.risk_score,
        "request_envelope": bundle.request_envelope,
        "retrieved_documents": [
            {"doc_id": doc_id, "content_sha256": sha}
            for doc_id, sha in bundle.retrieved_documents
        ],
        "tool_io": list(bundle.tool_io),
        "policy_evaluations": [
            {
                "package": p.package,
                "decision": p.decision,
                "reason": p.reason,
            }
            for p in bundle.policy_evaluations
        ],
        "triad_review": (
            None
            if bundle.triad_review is None
            else {
                "consensus_kind": bundle.triad_review.consensus_kind,
                "agreed_decision": bundle.triad_review.agreed_decision,
                "verdicts": [
                    {
                        "reviewer_id": rid,
                        "decision": dec,
                        "confidence": conf,
                        "reasoning": reas,
                    }
                    for rid, dec, conf, reas in bundle.triad_review.verdicts
                ],
                "commitments": [
                    {"reviewer_id": rid, "sha256_hex": h}
                    for rid, h in bundle.triad_review.commitments
                ],
            }
        ),
        "timestamp_unix_ns": bundle.timestamp_unix_ns,
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def deserialise_bundle(payload_bytes: bytes) -> ReplayBundle:
    """Inverse of canonicalise_bundle.

    Strict: rejects payloads whose schema_version doesn't match this
    module's BUNDLE_SCHEMA_VERSION; we don't try to upcast/downcast.
    Phase 1 will add a versioned dispatch when the schema first
    changes incompatibly.

    Raises ValueError on malformed payload (missing required fields,
    wrong types, unknown schema_version).
    """
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"payload is not valid UTF-8 JSON: {e!s}") from e
    if not isinstance(payload, dict):
        raise ValueError(
            f"payload must be a JSON object; got {type(payload).__name__}"
        )
    required = {
        "schema_version", "audit_id", "tenant_id", "decision",
        "risk_score", "request_envelope", "retrieved_documents",
        "tool_io", "policy_evaluations", "triad_review",
        "timestamp_unix_ns",
    }
    missing = required - set(payload.keys())
    if missing:
        raise ValueError(
            f"payload missing required fields: {sorted(missing)}"
        )

    schema_version = payload["schema_version"]
    if schema_version != BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {schema_version!r}; "
            f"this module supports only {BUNDLE_SCHEMA_VERSION}"
        )

    triad_raw = payload["triad_review"]
    if triad_raw is None:
        triad: TriadReviewRecord | None = None
    else:
        triad = TriadReviewRecord(
            consensus_kind=triad_raw["consensus_kind"],
            agreed_decision=triad_raw["agreed_decision"],
            verdicts=tuple(
                (
                    v["reviewer_id"],
                    v["decision"],
                    float(v["confidence"]),
                    v["reasoning"],
                )
                for v in triad_raw["verdicts"]
            ),
            commitments=tuple(
                (c["reviewer_id"], c["sha256_hex"])
                for c in triad_raw["commitments"]
            ),
        )

    policy_evals = tuple(
        PolicyEvaluationRecord(
            package=p["package"],
            decision=p["decision"],
            reason=p["reason"],
        )
        for p in payload["policy_evaluations"]
    )

    retrieved = tuple(
        (d["doc_id"], d["content_sha256"])
        for d in payload["retrieved_documents"]
    )

    return ReplayBundle(
        audit_id=uuid.UUID(payload["audit_id"]),
        tenant_id=uuid.UUID(payload["tenant_id"]),
        decision=payload["decision"],
        risk_score=float(payload["risk_score"]),
        request_envelope=payload["request_envelope"],
        retrieved_documents=retrieved,
        tool_io=tuple(payload["tool_io"]),
        policy_evaluations=policy_evals,
        triad_review=triad,
        timestamp_unix_ns=int(payload["timestamp_unix_ns"]),
        schema_version=schema_version,
    )
