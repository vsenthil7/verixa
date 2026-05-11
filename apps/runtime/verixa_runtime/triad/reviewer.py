"""Reviewer client abstraction (CP-10.2).

A "reviewer" is a model that, given a governed-action prompt, returns
a ReviewerVerdict. The triad protocol (CP-10.1) is independent of how
the verdict is produced -- whether by vLLM-on-ROCm against MI300X, by
HF Inference Endpoints, or by a deterministic mock for tests.

Two implementations ship in CP-10.2:

  - OpenAICompatReviewer -- async HTTP client that POSTs to a
    vLLM-on-ROCm /v1/chat/completions endpoint (OpenAI-compatible).
    Configurable model name, system prompt, temperature, timeout, and
    base URL. Produces a verdict by parsing a JSON-shaped reply; on
    parse failure the reviewer abstains by returning a verdict with
    decision=ESCALATE and a low confidence (the orchestrator surfaces
    this as the model declining to commit).

  - MockReviewer -- in-memory deterministic reviewer; takes a
    pre-baked verdict factory. Used by orchestrator tests
    (CP-10.3) and as the hackathon fallback when the droplet is
    unreachable.

The orchestrator (CP-10.3) holds three reviewer instances -- typically
three OpenAICompatReviewer with different system prompts to give each
slot a distinct "personality" -- runs them in parallel, drives the
commit-reveal protocol, and computes consensus.

Phase-0 architectural deviation:

  The page-1 brief specifies Qwen3-72B + Llama-3.3-70B + DeepSeek-V3
  as the three reviewer models. The MI300X droplet at
  ``http://165.245.133.120:8000`` currently serves Qwen3-0.6B only.
  Phase-0 ships three slots backed by the same Qwen3-0.6B with three
  different system prompts (conservative, pragmatic, sceptical) so
  the triad protocol's commit-reveal + consensus surface is fully
  exercised on the live MI300X path. The protocol is model-agnostic;
  swapping in three larger distinct models is a config change, not
  a code change.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

import httpx

from verixa_runtime.triad.protocol import (
    ReviewerId,
    ReviewerVerdict,
    VerdictDecision,
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ReviewerError(RuntimeError):
    """Raised on transport / non-2xx / response-shape failures.

    The orchestrator catches this and converts to an ESCALATE verdict
    so a single reviewer outage doesn't take the triad down -- the
    commit-reveal protocol still runs with whatever reviewers
    succeeded, and missing reviewers surface as INTEGRITY_FAILURE in
    consensus.
    """


# ---------------------------------------------------------------------------
# Config + Protocol
# ---------------------------------------------------------------------------


# The default chat-completions path on vLLM-on-ROCm matches OpenAI's.
_OPENAI_CHAT_PATH: Final[str] = "/v1/chat/completions"


@dataclass(frozen=True, slots=True)
class ReviewerConfig:
    """Configuration for an OpenAICompatReviewer slot.

    ``base_url`` -- e.g. ``http://165.245.133.120:8000`` (no trailing
                    slash; we add the path).
    ``model``    -- the served model id (e.g. ``Qwen/Qwen3-0.6B``).
    ``reviewer_id`` -- which slot this reviewer fills.
    ``system_prompt`` -- the persona / verdict-rendering instructions;
                    differentiates Phase-0 slots that share a model.
    ``temperature`` -- 0.0 for deterministic verdicts (default); higher
                    only when modelling reviewer disagreement.
    ``timeout_seconds`` -- per-request timeout. vLLM on a small model
                    is fast; default 30s gives headroom for the first
                    cold call.
    """

    base_url: str
    model: str
    reviewer_id: ReviewerId
    system_prompt: str
    temperature: float = 0.0
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ValueError("base_url must be non-empty")
        if not self.model:
            raise ValueError("model must be non-empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                f"temperature must be in [0.0, 2.0]; got {self.temperature!r}"
            )
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class Reviewer(Protocol):
    """Reviewer surface used by the orchestrator (CP-10.3)."""

    @property
    def reviewer_id(self) -> ReviewerId:  # pragma: no cover
        # Protocol method body is unreachable -- structural typing
        # only; concrete classes provide the real implementation.
        ...

    async def review(
        self, *, audit_id: uuid.UUID, governed_action_summary: str
    ) -> ReviewerVerdict:  # pragma: no cover
        # Protocol method body is unreachable; see above.
        ...


# ---------------------------------------------------------------------------
# Live OpenAI-compat reviewer (vLLM-on-ROCm or any /v1/chat/completions)
# ---------------------------------------------------------------------------


_VERDICT_INSTRUCTION: Final[str] = (
    "Reply with ONLY a single JSON object on one line, no prose, no markdown, "
    'with these fields: {"decision": "allow" | "deny" | "escalate", '
    '"confidence": <float between 0 and 1>, "reasoning": "<short string>"}.'
)


def _verdict_from_payload(
    payload: dict[str, Any], *, reviewer_id: ReviewerId, audit_id: uuid.UUID
) -> ReviewerVerdict:
    """Parse the model's JSON-shaped reply into a ReviewerVerdict.

    Defensive: missing/extra fields, wrong types, out-of-range
    confidence, and unknown decision values all raise ReviewerError so
    the orchestrator can react. The model is allowed to ABSTAIN by
    returning decision='escalate' -- that is a valid model output, not
    an error.
    """
    if not isinstance(payload, dict):
        raise ReviewerError(
            f"reviewer reply is not a JSON object: {type(payload).__name__}"
        )
    decision_raw = payload.get("decision")
    confidence_raw = payload.get("confidence")
    reasoning_raw = payload.get("reasoning")
    if decision_raw is None or confidence_raw is None or reasoning_raw is None:
        raise ReviewerError(
            f"reviewer reply missing required field; got keys={list(payload)}"
        )
    if not isinstance(decision_raw, str):
        raise ReviewerError(
            f"decision must be a string; got {type(decision_raw).__name__}"
        )
    try:
        decision = VerdictDecision(decision_raw.lower())
    except ValueError as e:
        raise ReviewerError(
            f"unknown decision value {decision_raw!r}; "
            f"expected one of {[d.value for d in VerdictDecision]}"
        ) from e
    if not isinstance(confidence_raw, int | float) or isinstance(
        confidence_raw, bool
    ):
        raise ReviewerError(
            f"confidence must be a number; got {type(confidence_raw).__name__}"
        )
    confidence = float(confidence_raw)
    if not 0.0 <= confidence <= 1.0:
        raise ReviewerError(
            f"confidence out of range [0.0, 1.0]; got {confidence!r}"
        )
    if not isinstance(reasoning_raw, str):
        raise ReviewerError(
            f"reasoning must be a string; got {type(reasoning_raw).__name__}"
        )
    return ReviewerVerdict(
        reviewer_id=reviewer_id,
        decision=decision,
        confidence=confidence,
        reasoning=reasoning_raw,
        audit_id=audit_id,
    )


def _parse_chat_completion_text(content: str) -> dict[str, Any]:
    """Extract the JSON object from the model's ``content`` string.

    The model is instructed to reply with raw JSON only, but small
    models sometimes wrap output in markdown fences or add a leading
    word. We strip a single layer of ```json ... ``` fences if
    present, then parse. Anything weirder than that raises ReviewerError
    and the orchestrator escalates.
    """
    s = content.strip()
    if s.startswith("```"):
        # Strip optional language tag (first line after the opening
        # fence) and any trailing backtick run.
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rstrip("`").rstrip()
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError as e:
        raise ReviewerError(
            f"reviewer reply is not valid JSON: {e.msg!s}"
        ) from e
    if not isinstance(parsed, dict):
        raise ReviewerError(
            f"reviewer reply is JSON but not an object: {type(parsed).__name__}"
        )
    return parsed


@dataclass(frozen=True, slots=True)
class OpenAICompatReviewer:
    """Live reviewer that POSTs to /v1/chat/completions.

    Uses httpx.AsyncClient internally (constructed per-call so the
    instance stays frozen + slots-friendly; for hot-path use the
    orchestrator can pass in a shared client via the ``client``
    argument to ``review``).
    """

    config: ReviewerConfig

    @property
    def reviewer_id(self) -> ReviewerId:
        return self.config.reviewer_id

    def _build_request(
        self, *, audit_id: uuid.UUID, governed_action_summary: str
    ) -> dict[str, Any]:
        user_msg = (
            f"Audit ID: {audit_id}\n\n"
            f"Governed action under review:\n{governed_action_summary}\n\n"
            f"{_VERDICT_INSTRUCTION}"
        )
        return {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "temperature": self.config.temperature,
            "max_tokens": 200,
        }

    async def review(
        self,
        *,
        audit_id: uuid.UUID,
        governed_action_summary: str,
        client: httpx.AsyncClient | None = None,
    ) -> ReviewerVerdict:
        """Run the reviewer; return a typed ReviewerVerdict.

        Raises ReviewerError on transport / HTTP / parse failures; the
        orchestrator (CP-10.3) catches and converts to a synthesised
        ESCALATE verdict so partial-triad outages still produce a
        well-formed audit trail.
        """
        url = self.config.base_url.rstrip("/") + _OPENAI_CHAT_PATH
        body = self._build_request(
            audit_id=audit_id,
            governed_action_summary=governed_action_summary,
        )
        timeout = self.config.timeout_seconds
        if client is None:
            async with httpx.AsyncClient(timeout=timeout) as _c:
                resp = await _post_for_reviewer(_c, url, body)
        else:
            resp = await _post_for_reviewer(client, url, body)
        try:
            choices = resp["choices"]
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ReviewerError(
                f"reviewer reply has no choices[0].message.content: {e!r}"
            ) from e
        if not isinstance(content, str):
            raise ReviewerError(
                f"reviewer reply content is not a string: "
                f"{type(content).__name__}"
            )
        payload = _parse_chat_completion_text(content)
        return _verdict_from_payload(
            payload,
            reviewer_id=self.config.reviewer_id,
            audit_id=audit_id,
        )


async def _post_for_reviewer(
    client: httpx.AsyncClient, url: str, body: dict[str, Any]
) -> dict[str, Any]:
    """POST body as JSON; raise ReviewerError on transport / non-2xx / non-JSON."""
    try:
        http_resp = await client.post(url, json=body)
    except httpx.HTTPError as e:
        raise ReviewerError(f"reviewer transport failure: {e!r}") from e
    if http_resp.status_code >= 400:
        raise ReviewerError(
            f"reviewer returned HTTP {http_resp.status_code}: "
            f"{http_resp.text[:200]!r}"
        )
    try:
        return http_resp.json()
    except ValueError as e:
        raise ReviewerError(
            f"reviewer returned non-JSON body: {e!r}"
        ) from e


# ---------------------------------------------------------------------------
# Mock reviewer (deterministic; for orchestrator tests + offline demo)
# ---------------------------------------------------------------------------


VerdictFactory = Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]]


@dataclass(frozen=True, slots=True)
class MockReviewer:
    """Deterministic reviewer for tests + offline demo.

    The factory receives (audit_id, governed_action_summary) and
    returns a ReviewerVerdict; this lets test setups vary verdicts by
    audit_id without sharing mutable state.
    """

    _reviewer_id: ReviewerId
    factory: VerdictFactory = field(repr=False)

    @property
    def reviewer_id(self) -> ReviewerId:
        return self._reviewer_id

    async def review(
        self, *, audit_id: uuid.UUID, governed_action_summary: str
    ) -> ReviewerVerdict:
        verdict = await self.factory(audit_id, governed_action_summary)
        # Defensive: factory must produce a verdict for the right slot,
        # otherwise orchestrator pairing breaks downstream.
        if verdict.reviewer_id != self._reviewer_id:
            raise ReviewerError(
                f"MockReviewer factory returned reviewer_id="
                f"{verdict.reviewer_id.value}, expected "
                f"{self._reviewer_id.value}"
            )
        return verdict
