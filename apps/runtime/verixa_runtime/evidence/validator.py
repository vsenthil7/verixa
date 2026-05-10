"""Evidence Validator (CP-11).

Answers the question: did the agent's claim actually come from the
retrieved documents, or did it make it up?

Phase-0 implementation is deliberately lightweight: a citation
presence check + a lexical-overlap score over content tokens. Full
multi-stage validation (embedding similarity, retrieval grounding,
contradiction detection via NLI models) lives in Phase 2's
``Evidence Validator V2`` module.

The validator is **pure** -- no I/O, no embeddings, no model calls.
It takes a claim string, the retrieved documents the agent had
access to, and the citations the agent chose to attach; it returns
an EvidenceCheck bundling the verdict kind, the overlap score,
and the cited document ids it actually grounded against.

The verdict kinds are:

  GROUNDED      -- at least one citation, lexical overlap with cited
                   documents is >= GROUND_THRESHOLD (default 0.30).
                   The claim is reasonably supported by the cited
                   evidence.
  UNGROUNDED    -- at least one citation but overlap is below the
                   threshold. The agent cited documents but the
                   claim's content words don't appear in them; the
                   citation is decorative, not substantive.
  NO_CITATION   -- the agent provided zero citations. We can't
                   evaluate grounding without something to ground
                   against; surface this distinctly so reviewers
                   know the agent never claimed any evidence.
  CONTRADICTED  -- a cited document contains content that
                   contradicts the claim. Phase-0 detects this via
                   a small set of negation markers (a Phase-2
                   contradiction detector replaces this with NLI).

Phase-0 deviation note: NLI-based contradiction detection (a small
RoBERTa-MNLI head, ~25M params) is well within MI300X capacity but
introduces a model dependency. The brief explicitly defers full
validation to Phase 2; Phase-0 ships the cheap-but-honest version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Final


class EvidenceVerdict(str, Enum):
    """Outcome of a grounding check."""

    GROUNDED = "grounded"
    UNGROUNDED = "ungrounded"
    NO_CITATION = "no_citation"
    CONTRADICTED = "contradicted"


# Below this overlap fraction, a cited claim is judged UNGROUNDED.
# 0.30 is a hand-picked Phase-0 default chosen to be lenient enough
# that paraphrased claims pass but strict enough that random
# citations don't. CP-? Phase 1 will A/B this against labelled data.
GROUND_THRESHOLD: Final[float] = 0.30

# Negation markers that flip the polarity of a sentence. A claim like
# "the loan was approved" matched against a document containing
# "the loan was not approved" should fire CONTRADICTED. This is a
# crude proxy for NLI; Phase 2 replaces it.
_NEGATION_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "not",
        "never",
        "no",
        "cannot",
        "won",
        "wouldn",
        "didn",
        "doesn",
        "isn",
        "wasn",
        "weren",
        "denied",
        "rejected",
        "refused",
    }
)

# Stop-words filtered out before computing lexical overlap. Without
# this, "the the the" matches every document. Conservative list --
# we want content words to dominate. Phase 1 may swap for a proper
# tokeniser.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "his",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "she",
        "such",
        "that",
        "the",
        "their",
        "there",
        "they",
        "this",
        "to",
        "was",
        "we",
        "were",
        "will",
        "with",
        "you",
        "your",
    }
)

# Tokeniser: split on non-alphanumeric, lowercase. Phase 1 can swap
# for a proper subword/word tokeniser if needed. Note: contractions
# like "won't" tokenise to "won" + "t"; the "won" form is in
# _NEGATION_TOKENS so the negation signal survives the tokeniser.
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    """A document the agent had access to during the action.

    ``doc_id`` is the stable identifier the agent cites; ``content``
    is the text against which we compute overlap. Phase-0 treats the
    content as a flat string; Phase 2 will split into chunks with
    individual offsets so citations can point to a specific span.
    """

    doc_id: str
    content: str

    def __post_init__(self) -> None:
        if not self.doc_id:
            raise ValueError("doc_id must be non-empty")


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    """Result of evaluating one claim against its citations."""

    verdict: EvidenceVerdict
    overlap_score: float
    cited_doc_ids: tuple[str, ...] = field(default_factory=tuple)
    contradicting_doc_ids: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.overlap_score <= 1.0:
            raise ValueError(
                f"overlap_score must be in [0.0, 1.0]; "
                f"got {self.overlap_score!r}"
            )


def _tokenise(text: str) -> set[str]:
    """Lowercase, split on non-alphanumeric, drop stop-words."""
    return {
        tok for tok in _TOKEN_RE.findall(text.lower())
        if tok not in _STOPWORDS
    }


def _lexical_overlap(
    claim_tokens: set[str], doc_tokens: set[str]
) -> float:
    """Fraction of claim's content tokens that appear in the document.

    Asymmetric on purpose: a long document mentioning a few of the
    claim's words isn't strong support; we want most of the claim's
    content words to be backed by the document. Range [0.0, 1.0].
    """
    if not claim_tokens:
        # An empty claim trivially "matches" nothing; treat as 0.0
        # rather than 1.0 to avoid auto-grounding empty content.
        return 0.0
    matched = claim_tokens & doc_tokens
    return len(matched) / len(claim_tokens)


def _contradicts(claim_tokens: set[str], doc_text: str) -> bool:
    """Detect a likely contradiction between claim and document.

    Phase-0 heuristic: split the document into sentences, and for
    each sentence check whether it contains a negation token AND
    substantial overlap with the claim's content tokens. The
    intuition is: a sentence that talks about the same things as
    the claim *but* contains a negation is likely refuting the
    claim. Phase 2 replaces with proper NLI.

    "substantial overlap" here is >=50% of claim tokens in the
    sentence -- much stricter than the general GROUND_THRESHOLD,
    since we want to be sure the sentence is actually about the
    same proposition before flipping the verdict.
    """
    if not claim_tokens:
        return False
    sentences = re.split(r"[.!?]+", doc_text.lower())
    for sentence in sentences:
        sentence_tokens = _tokenise(sentence)
        if not (sentence_tokens & _NEGATION_TOKENS):
            continue
        # Negation present; check if the rest of the sentence is
        # about the same content as the claim. Exclude the negation
        # tokens themselves so they don't spuriously inflate the
        # overlap.
        content_in_sentence = sentence_tokens - _NEGATION_TOKENS
        if not content_in_sentence:
            continue
        shared = claim_tokens & content_in_sentence
        if len(shared) / len(claim_tokens) >= 0.5:
            return True
    return False


def validate_evidence(
    claim: str,
    citations: list[str],
    documents: list[RetrievedDocument],
    *,
    ground_threshold: float = GROUND_THRESHOLD,
) -> EvidenceCheck:
    """Validate that ``claim`` is grounded in the cited ``documents``.

    Inputs:
      - ``claim``: the agent's natural-language claim.
      - ``citations``: doc_ids the agent attached to the claim. Empty
        list -> NO_CITATION; otherwise we score against the union of
        cited documents.
      - ``documents``: the documents the agent had access to. Only
        documents whose doc_id appears in ``citations`` are scored
        (the rest are noise from the agent's perspective).

    Rules:
      1. No citations -> NO_CITATION (overlap_score=0.0).
      2. Citations refer to doc_ids not present in ``documents`` ->
         those citations are dropped silently; if all citations are
         dangling, verdict is NO_CITATION.
      3. Compute lexical overlap between claim's content tokens and
         the union of cited documents' content tokens.
      4. Check each cited document individually for contradiction
         (negation + content overlap). If any cited doc contradicts,
         verdict is CONTRADICTED regardless of overall overlap --
         contradicting evidence trumps supporting evidence.
      5. Otherwise: overlap >= ground_threshold -> GROUNDED;
         else UNGROUNDED.

    Raises ValueError on ground_threshold outside [0.0, 1.0].
    """
    if not 0.0 <= ground_threshold <= 1.0:
        raise ValueError(
            f"ground_threshold must be in [0.0, 1.0]; "
            f"got {ground_threshold!r}"
        )

    # Filter dangling citations (cite an unknown doc_id).
    doc_by_id = {d.doc_id: d for d in documents}
    cited_docs = [doc_by_id[c] for c in citations if c in doc_by_id]

    if not cited_docs:
        reason = (
            "no citations provided"
            if not citations
            else "all citations referred to unknown documents"
        )
        return EvidenceCheck(
            verdict=EvidenceVerdict.NO_CITATION,
            overlap_score=0.0,
            reason=reason,
        )

    claim_tokens = _tokenise(claim)

    # Contradiction check first -- contradicting evidence trumps
    # supporting evidence even if overlap is high.
    contradicting = tuple(
        d.doc_id for d in cited_docs
        if _contradicts(claim_tokens, d.content)
    )

    # Lexical overlap against union of cited docs.
    union_tokens: set[str] = set()
    for d in cited_docs:
        union_tokens |= _tokenise(d.content)
    overlap = _lexical_overlap(claim_tokens, union_tokens)

    cited_ids = tuple(d.doc_id for d in cited_docs)

    if contradicting:
        return EvidenceCheck(
            verdict=EvidenceVerdict.CONTRADICTED,
            overlap_score=overlap,
            cited_doc_ids=cited_ids,
            contradicting_doc_ids=contradicting,
            reason=(
                f"cited document(s) {list(contradicting)} contain "
                f"negation aligned with the claim's content"
            ),
        )

    if overlap >= ground_threshold:
        return EvidenceCheck(
            verdict=EvidenceVerdict.GROUNDED,
            overlap_score=overlap,
            cited_doc_ids=cited_ids,
            reason=f"lexical overlap {overlap:.2f} >= {ground_threshold:.2f}",
        )

    return EvidenceCheck(
        verdict=EvidenceVerdict.UNGROUNDED,
        overlap_score=overlap,
        cited_doc_ids=cited_ids,
        reason=f"lexical overlap {overlap:.2f} < {ground_threshold:.2f}",
    )
