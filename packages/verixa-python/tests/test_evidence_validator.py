"""pytest suite for verixa_runtime.evidence.validator (CP-11.1).

Coverage strategy: pure-function module, no I/O, so all branches are
exercised by direct calls with fixtures.

Layers:
  1. Dataclass invariants -- RetrievedDocument doc_id non-empty,
     EvidenceCheck overlap_score 0..1.
  2. Tokeniser + overlap primitives (via behavioural tests on the
     public validate_evidence surface).
  3. validate_evidence verdict matrix:
     - NO_CITATION (empty citations list)
     - NO_CITATION (all citations dangle)
     - GROUNDED happy path
     - UNGROUNDED (citation present, no overlap)
     - CONTRADICTED (negation aligned with claim)
     - threshold knob (custom ground_threshold flips verdict)
     - empty claim never grounds
     - ground_threshold validation rejects out-of-range
"""

from __future__ import annotations

import pytest
from verixa_runtime.evidence import (
    GROUND_THRESHOLD,
    EvidenceCheck,
    EvidenceVerdict,
    RetrievedDocument,
    validate_evidence,
)

# ---------------------------------------------------------------------------
# Layer 1 -- dataclass invariants
# ---------------------------------------------------------------------------


def test_retrieved_document_doc_id_must_be_non_empty() -> None:
    with pytest.raises(ValueError, match="doc_id"):
        RetrievedDocument(doc_id="", content="x")


def test_retrieved_document_accepts_valid() -> None:
    d = RetrievedDocument(doc_id="d1", content="hello world")
    assert d.doc_id == "d1"
    assert d.content == "hello world"


def test_evidence_check_overlap_below_zero_rejected() -> None:
    with pytest.raises(ValueError, match="overlap_score"):
        EvidenceCheck(verdict=EvidenceVerdict.GROUNDED, overlap_score=-0.01)


def test_evidence_check_overlap_above_one_rejected() -> None:
    with pytest.raises(ValueError, match="overlap_score"):
        EvidenceCheck(verdict=EvidenceVerdict.GROUNDED, overlap_score=1.01)


def test_evidence_check_accepts_boundaries() -> None:
    EvidenceCheck(verdict=EvidenceVerdict.GROUNDED, overlap_score=0.0)
    EvidenceCheck(verdict=EvidenceVerdict.GROUNDED, overlap_score=1.0)


def test_evidence_check_default_fields() -> None:
    c = EvidenceCheck(verdict=EvidenceVerdict.NO_CITATION, overlap_score=0.0)
    assert c.cited_doc_ids == ()
    assert c.contradicting_doc_ids == ()
    assert c.reason == ""


# ---------------------------------------------------------------------------
# Layer 2 -- validate_evidence verdict matrix
# ---------------------------------------------------------------------------


def test_no_citation_when_citations_list_empty() -> None:
    docs = [RetrievedDocument(doc_id="d1", content="anything")]
    result = validate_evidence(
        claim="the sky is blue", citations=[], documents=docs
    )
    assert result.verdict == EvidenceVerdict.NO_CITATION
    assert result.overlap_score == pytest.approx(0.0)
    assert result.cited_doc_ids == ()
    assert "no citations" in result.reason


def test_no_citation_when_all_citations_dangle() -> None:
    docs = [RetrievedDocument(doc_id="d1", content="anything")]
    result = validate_evidence(
        claim="the sky is blue",
        citations=["d99", "d100"],
        documents=docs,
    )
    assert result.verdict == EvidenceVerdict.NO_CITATION
    assert "unknown documents" in result.reason


def test_grounded_happy_path() -> None:
    """Claim's content tokens all appear in the cited document."""
    docs = [
        RetrievedDocument(
            doc_id="d1",
            content=(
                "The loan application for customer 42 was approved "
                "by the credit committee on 2026-05-10."
            ),
        )
    ]
    result = validate_evidence(
        claim="loan application customer 42 approved credit committee",
        citations=["d1"],
        documents=docs,
    )
    assert result.verdict == EvidenceVerdict.GROUNDED
    assert result.overlap_score >= GROUND_THRESHOLD
    assert result.cited_doc_ids == ("d1",)


def test_ungrounded_citation_but_no_overlap() -> None:
    """Citation present but the document's content words don't match
    the claim."""
    docs = [
        RetrievedDocument(
            doc_id="d1",
            content="weather forecast for tomorrow rainy showers",
        )
    ]
    result = validate_evidence(
        claim="loan application customer approved credit committee",
        citations=["d1"],
        documents=docs,
    )
    assert result.verdict == EvidenceVerdict.UNGROUNDED
    assert result.overlap_score < GROUND_THRESHOLD
    assert result.cited_doc_ids == ("d1",)


def test_contradicted_negation_aligned_with_claim() -> None:
    """Document contains a sentence with negation + substantial
    overlap with the claim -> CONTRADICTED, even if other documents
    would have supported the claim."""
    docs = [
        RetrievedDocument(
            doc_id="d1",
            content=(
                "The loan application for customer 42 was not "
                "approved by the credit committee."
            ),
        )
    ]
    result = validate_evidence(
        claim="loan application customer 42 approved credit committee",
        citations=["d1"],
        documents=docs,
    )
    assert result.verdict == EvidenceVerdict.CONTRADICTED
    assert "d1" in result.contradicting_doc_ids


def test_contradicted_trumps_high_overlap() -> None:
    """One cited doc supports, one contradicts -> CONTRADICTED.

    Even though the supporting doc would yield high overall overlap,
    the contradicting doc wins."""
    docs = [
        RetrievedDocument(
            doc_id="d_support",
            content=(
                "The loan application for customer 42 was approved "
                "by the credit committee on 2026-05-10."
            ),
        ),
        RetrievedDocument(
            doc_id="d_contra",
            content=(
                "The loan application for customer 42 was denied "
                "by the credit committee on appeal."
            ),
        ),
    ]
    result = validate_evidence(
        claim="loan application customer 42 approved credit committee",
        citations=["d_support", "d_contra"],
        documents=docs,
    )
    assert result.verdict == EvidenceVerdict.CONTRADICTED
    assert result.contradicting_doc_ids == ("d_contra",)


def test_threshold_knob_flips_verdict() -> None:
    """A lenient threshold turns UNGROUNDED into GROUNDED.

    Build a case where the lexical overlap is roughly 0.20 -- below
    the default 0.30, so default is UNGROUNDED; lower the threshold
    to 0.15 and the verdict flips to GROUNDED."""
    docs = [
        RetrievedDocument(
            doc_id="d1",
            content="apple banana cherry date elderberry fig grape",
        )
    ]
    # Claim has 5 content tokens; only 1 ("banana") appears in doc.
    # Overlap = 1/5 = 0.20.
    result_default = validate_evidence(
        claim="banana xylophone yodel zebra rocket",
        citations=["d1"],
        documents=docs,
    )
    assert result_default.verdict == EvidenceVerdict.UNGROUNDED
    assert result_default.overlap_score == pytest.approx(0.2)

    result_lenient = validate_evidence(
        claim="banana xylophone yodel zebra rocket",
        citations=["d1"],
        documents=docs,
        ground_threshold=0.15,
    )
    assert result_lenient.verdict == EvidenceVerdict.GROUNDED
    assert result_lenient.overlap_score == pytest.approx(0.2)


def test_empty_claim_does_not_auto_ground() -> None:
    """An empty/stop-words-only claim yields overlap=0.0, not 1.0.

    Verdict is UNGROUNDED (citation present but no content tokens to
    score against)."""
    docs = [RetrievedDocument(doc_id="d1", content="any content")]
    result = validate_evidence(
        claim="the the the",  # all stop-words, no content tokens
        citations=["d1"],
        documents=docs,
    )
    assert result.verdict == EvidenceVerdict.UNGROUNDED
    assert result.overlap_score == pytest.approx(0.0)


def test_ground_threshold_validation_rejects_below_zero() -> None:
    with pytest.raises(ValueError, match="ground_threshold"):
        validate_evidence(
            claim="x",
            citations=[],
            documents=[],
            ground_threshold=-0.01,
        )


def test_ground_threshold_validation_rejects_above_one() -> None:
    with pytest.raises(ValueError, match="ground_threshold"):
        validate_evidence(
            claim="x",
            citations=[],
            documents=[],
            ground_threshold=1.01,
        )


def test_partially_dangling_citations_kept_for_known_docs() -> None:
    """Some citations dangle, some resolve -> only the resolved ones
    score."""
    docs = [
        RetrievedDocument(
            doc_id="d_real",
            content="customer 42 loan approved credit committee",
        )
    ]
    result = validate_evidence(
        claim="customer 42 loan approved",
        citations=["d_real", "d_dangling"],
        documents=docs,
    )
    assert result.verdict == EvidenceVerdict.GROUNDED
    assert result.cited_doc_ids == ("d_real",)


def test_contradiction_requires_negation_and_overlap() -> None:
    """A sentence with negation but no claim-content-overlap doesn't
    fire CONTRADICTED.

    Document contains 'never go there' but the claim is about loans;
    the negation is unrelated to the claim's content."""
    docs = [
        RetrievedDocument(
            doc_id="d1",
            content=(
                "Customer 42 loan was approved by credit committee. "
                "We will never go to that place again."
            ),
        )
    ]
    result = validate_evidence(
        claim="customer 42 loan approved credit committee",
        citations=["d1"],
        documents=docs,
    )
    assert result.verdict == EvidenceVerdict.GROUNDED
    assert result.contradicting_doc_ids == ()


def test_contradiction_skips_sentence_with_only_negation() -> None:
    """A sentence containing ONLY negation tokens (no content) cant
    contradict; loop continues."""
    docs = [
        RetrievedDocument(
            doc_id="d1",
            content=(
                "Customer 42 loan approved by committee. No. "
                "Definitely. Confirmed."
            ),
        )
    ]
    result = validate_evidence(
        claim="customer 42 loan approved committee",
        citations=["d1"],
        documents=docs,
    )
    # "No." sentence after negation-only filtering has empty content;
    # _contradicts loop must continue past it without firing.
    assert result.verdict == EvidenceVerdict.GROUNDED


def test_no_contradiction_when_claim_empty() -> None:
    """Empty claim_tokens -> _contradicts returns False immediately."""
    docs = [
        RetrievedDocument(
            doc_id="d1",
            content="this loan was not approved by the committee.",
        )
    ]
    result = validate_evidence(
        claim="the the the",  # all stopwords -> empty claim_tokens
        citations=["d1"],
        documents=docs,
    )
    # Empty claim -> overlap=0.0 -> UNGROUNDED, NOT contradicted
    # (the early-return in _contradicts skips the negation scan).
    assert result.verdict == EvidenceVerdict.UNGROUNDED
    assert result.contradicting_doc_ids == ()
