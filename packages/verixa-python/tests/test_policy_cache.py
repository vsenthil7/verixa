"""pytest suite for verixa_runtime.policy.cache (CP-8.5 + CP-8.6).

Uses an in-memory RedisLike stub so the test suite never depends on a
running Redis container. Live Redis integration runs separately under
the ``integration`` marker -- see test_policy_cache_integration.py.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from verixa_runtime.policy import client as client_module
from verixa_runtime.policy.cache import (
    CACHE_KEY_PREFIX,
    CACHE_TTL_SECONDS,
    CachedPolicyClient,
    CacheStats,
    _build_cache_key,
    _canonical_input_hash,
    _coerce_payload_to_str,
    _deserialise_decision,
    _serialise_decision,
)
from verixa_runtime.policy.client import (
    OpaPolicyClient,
    PolicyClientError,
    PolicyDecision,
    PolicyDecisionKind,
)


# ---------------------------------------------------------------------------
# In-memory RedisLike stub
# ---------------------------------------------------------------------------


class InMemoryRedisStub:
    """Satisfies the RedisLike Protocol: async get + setex.

    Returns ``str`` values (mirrors ``decode_responses=True`` default
    Verixa wires for production). The bytes-tolerant code path is
    exercised by ``InMemoryBytesRedisStub`` and the live integration
    tests.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.get_calls: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        return self.store.get(key)

    async def setex(
        self, key: str, ttl_seconds: int, value: str
    ) -> None:
        self.setex_calls.append((key, ttl_seconds, value))
        self.store[key] = value
        self.ttls[key] = ttl_seconds


class InMemoryBytesRedisStub:
    """Mimics ``redis.asyncio.Redis(decode_responses=False)``.

    ``get`` returns ``bytes``. The cache is required to UTF-8-decode
    transparently so a deployer who forgets ``decode_responses=True``
    doesn't get a silent crash.
    """

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    async def setex(
        self, key: str, ttl_seconds: int, value: str
    ) -> None:
        # redis.asyncio.setex accepts str OR bytes; production stores str.
        self.store[key] = value.encode("utf-8")


TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa01")
TENANT_B = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa02")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_opa_client_for_handler(
    monkeypatch: pytest.MonkeyPatch, handler
) -> OpaPolicyClient:
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        client_module.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=transport, **kw),
    )
    return OpaPolicyClient("http://opa:8181")


def _opa_pass_handler(call_count: list[int]):
    def _handler(request: httpx.Request) -> httpx.Response:
        call_count.append(1)
        return httpx.Response(
            200,
            json={
                "result": {
                    "decision": "pass",
                    "reason": "",
                    "policy": "verixa.fs.x",
                }
            },
        )

    return _handler


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_cache_constants() -> None:
    assert CACHE_TTL_SECONDS == 5
    assert CACHE_KEY_PREFIX == "verixa:policy"


# ---------------------------------------------------------------------------
# _canonical_input_hash + _build_cache_key
# ---------------------------------------------------------------------------


def test_canonical_input_hash_is_deterministic() -> None:
    a = _canonical_input_hash({"x": 1, "y": 2})
    b = _canonical_input_hash({"y": 2, "x": 1})  # different insertion order
    assert a == b
    assert len(a) == 64
    int(a, 16)  # hex


def test_canonical_input_hash_differs_for_different_inputs() -> None:
    a = _canonical_input_hash({"x": 1})
    b = _canonical_input_hash({"x": 2})
    assert a != b


def test_canonical_input_hash_sensitive_to_nested_changes() -> None:
    a = _canonical_input_hash({"action": {"tool_name": "transfer"}})
    b = _canonical_input_hash({"action": {"tool_name": "lookup"}})
    assert a != b


def test_build_cache_key_format() -> None:
    key = _build_cache_key(TENANT_A, "verixa.fs.x", {"y": 1})
    assert key.startswith(f"{CACHE_KEY_PREFIX}:{TENANT_A}:verixa.fs.x:")
    # Last segment is the 64-hex sha256
    last = key.rsplit(":", 1)[1]
    assert len(last) == 64


def test_build_cache_key_differs_per_tenant() -> None:
    k1 = _build_cache_key(TENANT_A, "verixa.fs.x", {"y": 1})
    k2 = _build_cache_key(TENANT_B, "verixa.fs.x", {"y": 1})
    assert k1 != k2


def test_build_cache_key_differs_per_package() -> None:
    k1 = _build_cache_key(TENANT_A, "verixa.fs.x", {"y": 1})
    k2 = _build_cache_key(TENANT_A, "verixa.fs.y", {"y": 1})
    assert k1 != k2


# ---------------------------------------------------------------------------
# _serialise / _deserialise round-trip + error paths
# ---------------------------------------------------------------------------


def test_serialise_round_trip_pass() -> None:
    d = PolicyDecision(
        decision=PolicyDecisionKind.PASS,
        reason="",
        raw={"matched_pattern": None},
    )
    payload = _serialise_decision(d)
    out = _deserialise_decision(payload)
    assert out.decision == PolicyDecisionKind.PASS
    assert out.reason == ""
    assert out.raw == {"matched_pattern": None}


def test_serialise_round_trip_fail_with_extras() -> None:
    d = PolicyDecision(
        decision=PolicyDecisionKind.FAIL,
        reason="amount above limit",
        raw={
            "matched_pattern": "amount",
            "policy": "verixa.fs.transfer_amount_limit",
        },
    )
    payload = _serialise_decision(d)
    out = _deserialise_decision(payload)
    assert out.decision == PolicyDecisionKind.FAIL
    assert out.reason == "amount above limit"
    assert out.raw["matched_pattern"] == "amount"


def test_serialise_round_trip_abstain() -> None:
    d = PolicyDecision(decision=PolicyDecisionKind.ABSTAIN, reason="undefined")
    payload = _serialise_decision(d)
    out = _deserialise_decision(payload)
    assert out.decision == PolicyDecisionKind.ABSTAIN


def test_deserialise_rejects_corrupt_json() -> None:
    with pytest.raises(PolicyClientError, match="corrupt cache"):
        _deserialise_decision("this is not json")


def test_deserialise_rejects_non_object() -> None:
    with pytest.raises(PolicyClientError, match="not a JSON object"):
        _deserialise_decision(json.dumps([1, 2]))


def test_deserialise_rejects_missing_decision() -> None:
    with pytest.raises(PolicyClientError, match="missing field 'decision'"):
        _deserialise_decision(json.dumps({"reason": ""}))


def test_deserialise_rejects_missing_reason() -> None:
    with pytest.raises(PolicyClientError, match="missing field 'reason'"):
        _deserialise_decision(json.dumps({"decision": "pass"}))


def test_deserialise_rejects_invalid_decision_value() -> None:
    with pytest.raises(PolicyClientError, match="invalid decision"):
        _deserialise_decision(
            json.dumps({"decision": "maybe", "reason": ""})
        )


def test_deserialise_rejects_non_object_raw() -> None:
    with pytest.raises(PolicyClientError, match="'raw' is not an object"):
        _deserialise_decision(
            json.dumps({"decision": "pass", "reason": "", "raw": [1, 2]})
        )


# ---------------------------------------------------------------------------
# CP-8.6: bytes-tolerance for redis.asyncio decode_responses=False deployers
# ---------------------------------------------------------------------------


def test_coerce_payload_passes_str_through() -> None:
    assert _coerce_payload_to_str("hello") == "hello"


def test_coerce_payload_decodes_utf8_bytes() -> None:
    assert _coerce_payload_to_str(b"hello") == "hello"


def test_coerce_payload_decodes_utf8_with_unicode() -> None:
    assert _coerce_payload_to_str("héllo".encode("utf-8")) == "héllo"


def test_coerce_payload_rejects_invalid_utf8() -> None:
    with pytest.raises(PolicyClientError, match="not valid UTF-8"):
        _coerce_payload_to_str(b"\xff\xfe\xfd invalid")


def test_deserialise_accepts_bytes_payload() -> None:
    """Real redis.asyncio with decode_responses=False returns bytes."""
    d = PolicyDecision(
        decision=PolicyDecisionKind.PASS, reason="ok", raw={}
    )
    payload_bytes = _serialise_decision(d).encode("utf-8")
    out = _deserialise_decision(payload_bytes)
    assert out.decision == PolicyDecisionKind.PASS
    assert out.reason == "ok"


def test_deserialise_bytes_corrupt_json_still_raises_correctly() -> None:
    with pytest.raises(PolicyClientError, match="corrupt cache"):
        _deserialise_decision(b"not even json")


def test_deserialise_bytes_invalid_utf8_raises_utf8_error() -> None:
    """Distinct error code path: bytes that aren't UTF-8 fail BEFORE JSON parse."""
    with pytest.raises(PolicyClientError, match="not valid UTF-8"):
        _deserialise_decision(b"\xff\xfe garbage")


@pytest.mark.asyncio
async def test_evaluate_handles_bytes_redis_get_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: a Redis client returning bytes (decode_responses=False)
    must not crash the cache hit path."""
    call_count: list[int] = []
    opa = _build_opa_client_for_handler(
        monkeypatch, _opa_pass_handler(call_count)
    )
    redis = InMemoryBytesRedisStub()
    c = CachedPolicyClient(opa, redis)
    input_doc = {"action": {"tool": "x"}}

    # First call: miss -> OPA -> setex (writes str-encoded as bytes by stub)
    await c.evaluate(TENANT_A, "verixa.fs.x", input_doc)
    # Second call: hit -> get returns bytes -> deserialise must decode
    decision = await c.evaluate(TENANT_A, "verixa.fs.x", input_doc)
    assert decision.decision == PolicyDecisionKind.PASS
    assert len(call_count) == 1  # one OPA call only
    assert c.stats == CacheStats(hits=1, misses=1)


# ---------------------------------------------------------------------------
# CachedPolicyClient construction
# ---------------------------------------------------------------------------


def test_init_default_ttl() -> None:
    redis = InMemoryRedisStub()
    opa = OpaPolicyClient("http://opa:8181")
    c = CachedPolicyClient(opa, redis)
    assert c.ttl_seconds == CACHE_TTL_SECONDS


def test_init_custom_ttl() -> None:
    redis = InMemoryRedisStub()
    opa = OpaPolicyClient("http://opa:8181")
    c = CachedPolicyClient(opa, redis, ttl_seconds=30)
    assert c.ttl_seconds == 30


def test_init_rejects_zero_ttl() -> None:
    redis = InMemoryRedisStub()
    opa = OpaPolicyClient("http://opa:8181")
    with pytest.raises(ValueError, match="positive"):
        CachedPolicyClient(opa, redis, ttl_seconds=0)


def test_init_rejects_negative_ttl() -> None:
    redis = InMemoryRedisStub()
    opa = OpaPolicyClient("http://opa:8181")
    with pytest.raises(ValueError, match="positive"):
        CachedPolicyClient(opa, redis, ttl_seconds=-5)


def test_initial_stats_zero() -> None:
    redis = InMemoryRedisStub()
    opa = OpaPolicyClient("http://opa:8181")
    c = CachedPolicyClient(opa, redis)
    assert c.stats == CacheStats(hits=0, misses=0)


# ---------------------------------------------------------------------------
# evaluate() -- cache miss / hit / TTL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_cache_miss_calls_opa_and_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count: list[int] = []
    opa = _build_opa_client_for_handler(
        monkeypatch, _opa_pass_handler(call_count)
    )
    redis = InMemoryRedisStub()
    c = CachedPolicyClient(opa, redis)

    decision = await c.evaluate(
        TENANT_A, "verixa.fs.x", {"action": {"tool_name": "transfer"}}
    )
    assert decision.decision == PolicyDecisionKind.PASS
    assert len(call_count) == 1  # one OPA round trip
    assert len(redis.setex_calls) == 1  # cached
    key, ttl, _ = redis.setex_calls[0]
    assert key.startswith(f"{CACHE_KEY_PREFIX}:{TENANT_A}:verixa.fs.x:")
    assert ttl == CACHE_TTL_SECONDS
    assert c.stats == CacheStats(hits=0, misses=1)


@pytest.mark.asyncio
async def test_evaluate_cache_hit_skips_opa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count: list[int] = []
    opa = _build_opa_client_for_handler(
        monkeypatch, _opa_pass_handler(call_count)
    )
    redis = InMemoryRedisStub()
    c = CachedPolicyClient(opa, redis)
    input_doc = {"action": {"tool_name": "transfer"}}

    # First call: miss
    await c.evaluate(TENANT_A, "verixa.fs.x", input_doc)
    # Second call (same tenant + package + input): hit
    decision = await c.evaluate(TENANT_A, "verixa.fs.x", input_doc)

    assert decision.decision == PolicyDecisionKind.PASS
    assert len(call_count) == 1  # OPA still only called once
    assert len(redis.setex_calls) == 1  # cache only written once
    assert c.stats == CacheStats(hits=1, misses=1)


@pytest.mark.asyncio
async def test_evaluate_different_inputs_separate_cache_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count: list[int] = []
    opa = _build_opa_client_for_handler(
        monkeypatch, _opa_pass_handler(call_count)
    )
    redis = InMemoryRedisStub()
    c = CachedPolicyClient(opa, redis)

    await c.evaluate(TENANT_A, "verixa.fs.x", {"action": {"tool": "a"}})
    await c.evaluate(TENANT_A, "verixa.fs.x", {"action": {"tool": "b"}})

    assert len(call_count) == 2
    assert c.stats == CacheStats(hits=0, misses=2)


@pytest.mark.asyncio
async def test_evaluate_different_tenants_separate_cache_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count: list[int] = []
    opa = _build_opa_client_for_handler(
        monkeypatch, _opa_pass_handler(call_count)
    )
    redis = InMemoryRedisStub()
    c = CachedPolicyClient(opa, redis)
    input_doc = {"action": {"tool_name": "transfer"}}

    await c.evaluate(TENANT_A, "verixa.fs.x", input_doc)
    await c.evaluate(TENANT_B, "verixa.fs.x", input_doc)

    assert len(call_count) == 2
    assert len(redis.setex_calls) == 2


@pytest.mark.asyncio
async def test_evaluate_custom_ttl_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count: list[int] = []
    opa = _build_opa_client_for_handler(
        monkeypatch, _opa_pass_handler(call_count)
    )
    redis = InMemoryRedisStub()
    c = CachedPolicyClient(opa, redis, ttl_seconds=42)
    await c.evaluate(TENANT_A, "verixa.fs.x", {"y": 1})
    _, ttl, _ = redis.setex_calls[0]
    assert ttl == 42


@pytest.mark.asyncio
async def test_evaluate_rejects_non_uuid_tenant_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count: list[int] = []
    opa = _build_opa_client_for_handler(
        monkeypatch, _opa_pass_handler(call_count)
    )
    redis = InMemoryRedisStub()
    c = CachedPolicyClient(opa, redis)
    with pytest.raises(ValueError, match="must be uuid.UUID"):
        await c.evaluate("not-a-uuid", "verixa.fs.x", {})  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_evaluate_propagates_opa_errors_uncached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient OPA failure must NOT poison the cache."""
    def _failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("opa down")

    opa = _build_opa_client_for_handler(monkeypatch, _failing_handler)
    redis = InMemoryRedisStub()
    c = CachedPolicyClient(opa, redis)
    with pytest.raises(PolicyClientError):
        await c.evaluate(TENANT_A, "verixa.fs.x", {"y": 1})
    assert redis.setex_calls == []  # nothing was cached
    assert c.stats == CacheStats(hits=0, misses=1)


@pytest.mark.asyncio
async def test_evaluate_returns_deserialised_pass_from_cache() -> None:
    """When cache pre-populated, evaluate() returns the parsed decision
    without ever hitting OPA -- using AsyncMock to detect any call."""
    redis = InMemoryRedisStub()
    # Pre-populate the cache
    key = _build_cache_key(TENANT_A, "verixa.fs.x", {"y": 1})
    redis.store[key] = _serialise_decision(
        PolicyDecision(
            decision=PolicyDecisionKind.FAIL,
            reason="precomputed deny",
            raw={"matched_pattern": "amount"},
        )
    )

    # OPA client whose evaluate would explode if called
    opa = OpaPolicyClient("http://opa:8181")
    opa.evaluate = AsyncMock(side_effect=AssertionError("OPA must not be called"))  # type: ignore[method-assign]

    c = CachedPolicyClient(opa, redis)
    out = await c.evaluate(TENANT_A, "verixa.fs.x", {"y": 1})

    assert out.decision == PolicyDecisionKind.FAIL
    assert out.reason == "precomputed deny"
    assert out.raw["matched_pattern"] == "amount"
    opa.evaluate.assert_not_awaited()
    assert c.stats == CacheStats(hits=1, misses=0)


# ---------------------------------------------------------------------------
# CacheStats + reexports
# ---------------------------------------------------------------------------


def test_cache_stats_is_frozen() -> None:
    s = CacheStats(hits=1, misses=2)
    with pytest.raises((AttributeError, Exception)):
        s.hits = 99  # type: ignore[misc]


def test_policy_package_reexports_cache() -> None:
    from verixa_runtime import policy

    for name in (
        "CACHE_KEY_PREFIX",
        "CACHE_TTL_SECONDS",
        "CacheStats",
        "CachedPolicyClient",
        "RedisLike",
    ):
        assert hasattr(policy, name), f"policy package missing {name}"
