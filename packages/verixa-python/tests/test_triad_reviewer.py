"""pytest suite for verixa_runtime.triad.reviewer (CP-10.2).

Coverage strategy mirrors CP-8.3 (policy/client.py): no live OPA, no
live droplet -- httpx.MockTransport simulates the /v1/chat/completions
upstream and lets us exercise every parse / error branch.

Layers:
  1. ReviewerConfig validation (every reject path).
  2. _verdict_from_payload (every accept + every reject path).
  3. _parse_chat_completion_text (raw JSON, fenced JSON, malformed).
  4. OpenAICompatReviewer end-to-end via MockTransport (happy path,
     transport error, HTTP 4xx, non-JSON body, missing-choices,
     non-string content).
  5. MockReviewer (happy path + reviewer_id mismatch defence).
  6. Reviewer Protocol structural typing (smoke).

Coverage target: 100% line + branch on
verixa_runtime/triad/reviewer.py.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from verixa_runtime.triad import (
    MockReviewer,
    OpenAICompatReviewer,
    Reviewer,
    ReviewerConfig,
    ReviewerError,
    ReviewerId,
    ReviewerVerdict,
    VerdictDecision,
)
from verixa_runtime.triad.reviewer import (
    _parse_chat_completion_text,
    _verdict_from_payload,
)

# Note: pyproject.toml configures pytest-asyncio mode='auto' so async
# def tests run automatically without an explicit marker. We do NOT
# set a module-level pytestmark here -- doing so would mark every
# (sync) helper test as asyncio and emit dozens of warnings.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_AUDIT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _config(
    *,
    base_url: str = "http://165.245.133.120:8000",
    model: str = "Qwen/Qwen3-0.6B",
    reviewer_id: ReviewerId = ReviewerId.REVIEWER_A,
    system_prompt: str = "You are a careful reviewer.",
    temperature: float = 0.0,
    timeout_seconds: float = 30.0,
) -> ReviewerConfig:
    return ReviewerConfig(
        base_url=base_url,
        model=model,
        reviewer_id=reviewer_id,
        system_prompt=system_prompt,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )


def _ok_chat_completion_body(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-x",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Layer 1: ReviewerConfig validation
# ---------------------------------------------------------------------------


def test_config_rejects_empty_base_url() -> None:
    with pytest.raises(ValueError, match="base_url"):
        _config(base_url="")


def test_config_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="model"):
        _config(model="")


def test_config_rejects_negative_temperature() -> None:
    with pytest.raises(ValueError, match="temperature"):
        _config(temperature=-0.01)


def test_config_rejects_temperature_above_two() -> None:
    with pytest.raises(ValueError, match="temperature"):
        _config(temperature=2.01)


def test_config_rejects_zero_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        _config(timeout_seconds=0)


def test_config_rejects_negative_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        _config(timeout_seconds=-1)


def test_config_accepts_temperature_boundaries() -> None:
    _config(temperature=0.0)
    _config(temperature=2.0)


# ---------------------------------------------------------------------------
# Layer 2: _verdict_from_payload
# ---------------------------------------------------------------------------


def _payload(**overrides: Any) -> dict[str, Any]:
    base = {"decision": "allow", "confidence": 0.9, "reasoning": "ok"}
    base.update(overrides)
    return base


def test_verdict_payload_happy_path() -> None:
    v = _verdict_from_payload(
        _payload(),
        reviewer_id=ReviewerId.REVIEWER_A,
        audit_id=_AUDIT_ID,
    )
    assert v.decision == VerdictDecision.ALLOW
    assert v.confidence == pytest.approx(0.9)
    assert v.reasoning == "ok"
    assert v.reviewer_id == ReviewerId.REVIEWER_A


def test_verdict_payload_decision_uppercase_normalised() -> None:
    v = _verdict_from_payload(
        _payload(decision="DENY"),
        reviewer_id=ReviewerId.REVIEWER_B,
        audit_id=_AUDIT_ID,
    )
    assert v.decision == VerdictDecision.DENY


def test_verdict_payload_int_confidence_coerced() -> None:
    v = _verdict_from_payload(
        _payload(confidence=1),
        reviewer_id=ReviewerId.REVIEWER_A,
        audit_id=_AUDIT_ID,
    )
    assert v.confidence == pytest.approx(1.0)


def test_verdict_payload_not_a_dict_rejected() -> None:
    with pytest.raises(ReviewerError, match="not a JSON object"):
        _verdict_from_payload(
            ["allow"],  # type: ignore[arg-type]
            reviewer_id=ReviewerId.REVIEWER_A,
            audit_id=_AUDIT_ID,
        )


def test_verdict_payload_missing_decision_rejected() -> None:
    bad = _payload()
    del bad["decision"]
    with pytest.raises(ReviewerError, match="missing required field"):
        _verdict_from_payload(
            bad,
            reviewer_id=ReviewerId.REVIEWER_A,
            audit_id=_AUDIT_ID,
        )


def test_verdict_payload_missing_confidence_rejected() -> None:
    bad = _payload()
    del bad["confidence"]
    with pytest.raises(ReviewerError, match="missing required field"):
        _verdict_from_payload(
            bad, reviewer_id=ReviewerId.REVIEWER_A, audit_id=_AUDIT_ID
        )


def test_verdict_payload_missing_reasoning_rejected() -> None:
    bad = _payload()
    del bad["reasoning"]
    with pytest.raises(ReviewerError, match="missing required field"):
        _verdict_from_payload(
            bad, reviewer_id=ReviewerId.REVIEWER_A, audit_id=_AUDIT_ID
        )


def test_verdict_payload_decision_wrong_type_rejected() -> None:
    with pytest.raises(ReviewerError, match="decision must be a string"):
        _verdict_from_payload(
            _payload(decision=1),
            reviewer_id=ReviewerId.REVIEWER_A,
            audit_id=_AUDIT_ID,
        )


def test_verdict_payload_unknown_decision_rejected() -> None:
    with pytest.raises(ReviewerError, match="unknown decision value"):
        _verdict_from_payload(
            _payload(decision="maybe"),
            reviewer_id=ReviewerId.REVIEWER_A,
            audit_id=_AUDIT_ID,
        )


def test_verdict_payload_confidence_wrong_type_rejected() -> None:
    with pytest.raises(ReviewerError, match="confidence must be a number"):
        _verdict_from_payload(
            _payload(confidence="high"),
            reviewer_id=ReviewerId.REVIEWER_A,
            audit_id=_AUDIT_ID,
        )


def test_verdict_payload_confidence_bool_rejected() -> None:
    """bool is a subclass of int in Python; we must reject it explicitly
    so True/False can't sneak past the number check."""
    with pytest.raises(ReviewerError, match="confidence must be a number"):
        _verdict_from_payload(
            _payload(confidence=True),
            reviewer_id=ReviewerId.REVIEWER_A,
            audit_id=_AUDIT_ID,
        )


def test_verdict_payload_confidence_below_zero_rejected() -> None:
    with pytest.raises(ReviewerError, match="confidence out of range"):
        _verdict_from_payload(
            _payload(confidence=-0.1),
            reviewer_id=ReviewerId.REVIEWER_A,
            audit_id=_AUDIT_ID,
        )


def test_verdict_payload_confidence_above_one_rejected() -> None:
    with pytest.raises(ReviewerError, match="confidence out of range"):
        _verdict_from_payload(
            _payload(confidence=1.1),
            reviewer_id=ReviewerId.REVIEWER_A,
            audit_id=_AUDIT_ID,
        )


def test_verdict_payload_reasoning_wrong_type_rejected() -> None:
    with pytest.raises(ReviewerError, match="reasoning must be a string"):
        _verdict_from_payload(
            _payload(reasoning=42),
            reviewer_id=ReviewerId.REVIEWER_A,
            audit_id=_AUDIT_ID,
        )


# ---------------------------------------------------------------------------
# Layer 3: _parse_chat_completion_text
# ---------------------------------------------------------------------------


def test_parse_text_raw_json() -> None:
    payload = _parse_chat_completion_text(
        '{"decision":"allow","confidence":0.5,"reasoning":"r"}'
    )
    assert payload == {"decision": "allow", "confidence": 0.5, "reasoning": "r"}


def test_parse_text_fenced_json_with_lang_tag() -> None:
    fenced = "```json\n{\"decision\":\"allow\",\"confidence\":0.5,\"reasoning\":\"r\"}\n```"
    payload = _parse_chat_completion_text(fenced)
    assert payload["decision"] == "allow"


def test_parse_text_fenced_json_without_lang_tag() -> None:
    fenced = "```\n{\"decision\":\"deny\",\"confidence\":0.1,\"reasoning\":\"x\"}\n```"
    payload = _parse_chat_completion_text(fenced)
    assert payload["decision"] == "deny"


def test_parse_text_invalid_json_rejected() -> None:
    with pytest.raises(ReviewerError, match="not valid JSON"):
        _parse_chat_completion_text("not even close")


def test_parse_text_json_array_rejected() -> None:
    with pytest.raises(ReviewerError, match="not an object"):
        _parse_chat_completion_text("[1,2,3]")


# ---------------------------------------------------------------------------
# Layer 4: OpenAICompatReviewer end-to-end via MockTransport
# ---------------------------------------------------------------------------


def _mock_transport(handler: Any) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient backed by a MockTransport handler."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_openai_compat_reviewer_happy_path_with_injected_client() -> None:
    """Happy path -- 200 OK with valid JSON content. Use the
    injected-client path so we control the transport."""
    raw_content = json.dumps(
        {"decision": "allow", "confidence": 0.85, "reasoning": "looks fine"}
    )

    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_ok_chat_completion_body(raw_content))

    reviewer = OpenAICompatReviewer(config=_config())
    async with _mock_transport(handler) as client:
        v = await reviewer.review(
            audit_id=_AUDIT_ID,
            governed_action_summary="transfer 1000 to acct 42",
            client=client,
        )
    assert v.decision == VerdictDecision.ALLOW
    assert v.confidence == pytest.approx(0.85)
    assert v.audit_id == _AUDIT_ID
    assert v.reviewer_id == ReviewerId.REVIEWER_A
    # Sanity-check the request the reviewer actually issued.
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["body"]["model"] == "Qwen/Qwen3-0.6B"
    assert seen["body"]["temperature"] == 0.0
    assert seen["body"]["messages"][0]["role"] == "system"
    assert seen["body"]["messages"][1]["role"] == "user"
    assert "transfer 1000" in seen["body"]["messages"][1]["content"]


async def test_openai_compat_reviewer_happy_path_no_injected_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover the ``client is None`` branch by monkey-patching httpx.AsyncClient
    so it returns our MockTransport-backed client."""
    raw_content = json.dumps(
        {"decision": "deny", "confidence": 0.99, "reasoning": "blocked"}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_chat_completion_body(raw_content))

    real_async_client = httpx.AsyncClient

    def fake_async_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        # Drop incoming kwargs (timeout etc.) and use our transport.
        return real_async_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(
        "verixa_runtime.triad.reviewer.httpx.AsyncClient", fake_async_client
    )

    reviewer = OpenAICompatReviewer(config=_config())
    v = await reviewer.review(
        audit_id=_AUDIT_ID,
        governed_action_summary="x",
    )
    assert v.decision == VerdictDecision.DENY


async def test_openai_compat_reviewer_strips_trailing_slash_in_base_url() -> None:
    captured_url: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_url["u"] = str(request.url)
        return httpx.Response(
            200,
            json=_ok_chat_completion_body(
                json.dumps(
                    {"decision": "allow", "confidence": 0.5, "reasoning": "r"}
                )
            ),
        )

    reviewer = OpenAICompatReviewer(
        config=_config(base_url="http://example.com:8000/")
    )
    async with _mock_transport(handler) as client:
        await reviewer.review(
            audit_id=_AUDIT_ID,
            governed_action_summary="x",
            client=client,
        )
    # No double slash before /v1.
    assert captured_url["u"] == "http://example.com:8000/v1/chat/completions"


async def test_openai_compat_reviewer_transport_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    reviewer = OpenAICompatReviewer(config=_config())
    async with _mock_transport(handler) as client:
        with pytest.raises(ReviewerError, match="transport failure"):
            await reviewer.review(
                audit_id=_AUDIT_ID,
                governed_action_summary="x",
                client=client,
            )


async def test_openai_compat_reviewer_http_4xx_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request")

    reviewer = OpenAICompatReviewer(config=_config())
    async with _mock_transport(handler) as client:
        with pytest.raises(ReviewerError, match="HTTP 400"):
            await reviewer.review(
                audit_id=_AUDIT_ID,
                governed_action_summary="x",
                client=client,
            )


async def test_openai_compat_reviewer_non_json_body_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not json",
            headers={"content-type": "text/plain"},
        )

    reviewer = OpenAICompatReviewer(config=_config())
    async with _mock_transport(handler) as client:
        with pytest.raises(ReviewerError, match="non-JSON"):
            await reviewer.review(
                audit_id=_AUDIT_ID,
                governed_action_summary="x",
                client=client,
            )


async def test_openai_compat_reviewer_missing_choices_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "x"})  # no choices

    reviewer = OpenAICompatReviewer(config=_config())
    async with _mock_transport(handler) as client:
        with pytest.raises(ReviewerError, match="choices"):
            await reviewer.review(
                audit_id=_AUDIT_ID,
                governed_action_summary="x",
                client=client,
            )


async def test_openai_compat_reviewer_non_string_content_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # content present but not a string
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": ["unexpected", "list"]}}]
            },
        )

    reviewer = OpenAICompatReviewer(config=_config())
    async with _mock_transport(handler) as client:
        with pytest.raises(ReviewerError, match="content is not a string"):
            await reviewer.review(
                audit_id=_AUDIT_ID,
                governed_action_summary="x",
                client=client,
            )


async def test_openai_compat_reviewer_propagates_invalid_inner_payload() -> None:
    """End-to-end: HTTP 200, choices/content are well-formed, but the
    inner JSON payload has a bad confidence value -- _verdict_from_payload
    should bubble up through review()."""
    raw_content = json.dumps(
        {"decision": "allow", "confidence": 5.0, "reasoning": "r"}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_chat_completion_body(raw_content))

    reviewer = OpenAICompatReviewer(config=_config())
    async with _mock_transport(handler) as client:
        with pytest.raises(ReviewerError, match="confidence out of range"):
            await reviewer.review(
                audit_id=_AUDIT_ID,
                governed_action_summary="x",
                client=client,
            )


# ---------------------------------------------------------------------------
# Layer 5: MockReviewer
# ---------------------------------------------------------------------------


async def test_mock_reviewer_happy_path() -> None:
    async def factory(audit_id: uuid.UUID, _summary: str) -> ReviewerVerdict:
        return ReviewerVerdict(
            reviewer_id=ReviewerId.REVIEWER_C,
            decision=VerdictDecision.ESCALATE,
            confidence=0.4,
            reasoning="unsure",
            audit_id=audit_id,
        )

    mock = MockReviewer(_reviewer_id=ReviewerId.REVIEWER_C, factory=factory)
    v = await mock.review(audit_id=_AUDIT_ID, governed_action_summary="x")
    assert v.reviewer_id == ReviewerId.REVIEWER_C
    assert v.decision == VerdictDecision.ESCALATE
    assert mock.reviewer_id == ReviewerId.REVIEWER_C


async def test_mock_reviewer_factory_id_mismatch_rejected() -> None:
    async def factory(audit_id: uuid.UUID, _summary: str) -> ReviewerVerdict:
        # Wrong reviewer_id on purpose.
        return ReviewerVerdict(
            reviewer_id=ReviewerId.REVIEWER_A,
            decision=VerdictDecision.ALLOW,
            confidence=1.0,
            reasoning="ok",
            audit_id=audit_id,
        )

    mock = MockReviewer(_reviewer_id=ReviewerId.REVIEWER_B, factory=factory)
    with pytest.raises(ReviewerError, match="reviewer_id="):
        await mock.review(audit_id=_AUDIT_ID, governed_action_summary="x")


# ---------------------------------------------------------------------------
# Layer 6: Reviewer Protocol (smoke -- structural typing must accept both)
# ---------------------------------------------------------------------------


def test_protocol_accepts_both_implementations() -> None:
    """Both concrete implementations satisfy the Reviewer Protocol."""

    async def factory(_a: uuid.UUID, _s: str) -> ReviewerVerdict:
        return ReviewerVerdict(
            reviewer_id=ReviewerId.REVIEWER_A,
            decision=VerdictDecision.ALLOW,
            confidence=1.0,
            reasoning="ok",
            audit_id=_AUDIT_ID,
        )

    live: Reviewer = OpenAICompatReviewer(config=_config())
    mock: Reviewer = MockReviewer(
        _reviewer_id=ReviewerId.REVIEWER_A, factory=factory
    )
    assert live.reviewer_id == ReviewerId.REVIEWER_A
    assert mock.reviewer_id == ReviewerId.REVIEWER_A
