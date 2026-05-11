"""Verixa Evidence Validator.

Phase-0 lightweight claim-vs-retrieved-document grounding check.
See validator.py for the full design rationale.
"""

from verixa_runtime.evidence.validator import (  # noqa: F401
    GROUND_THRESHOLD,
    EvidenceCheck,
    EvidenceVerdict,
    RetrievedDocument,
    validate_evidence,
)

__all__ = [
    "GROUND_THRESHOLD",
    "EvidenceCheck",
    "EvidenceVerdict",
    "RetrievedDocument",
    "validate_evidence",
]
