"""Redis-backed 5-second decision cache for the OPA policy client.

Wraps ``OpaPolicyClient.evaluate`` with a short-TTL cache so that
identical decision requests within a 5-second window share a single
OPA round-trip. The cache window is intentionally short:

  - long enough to absorb intra-request fan-out (one user action ->
    many policy evaluations from different gateway middleware layers
    sharing the same input)
  - short enough that policy bundle updates propagate within a few
    seconds without an explicit invalidation step

Cache key: ``verixa:policy:{tenant_id}:{package}:{input_hash}`` where
``input_hash`` is SHA-256(canonical-JSON(input_doc)) hex-encoded.

Cache value: JSON object mirroring the PolicyDecision shape:

    {
      "decision": "pass" | "fail" | "abstain",
      "reason": "<string>",
      "raw": <object>
    }

The wrapper is duck-typed against any object that exposes
``async get(key) -> str | bytes | None`` and
``async setex(key, ttl_seconds, value: str)`` so we can swap in the
``redis.asyncio`` client in production and a lightweight in-memory fake
in tests without conditional imports. ``get`` is permitted to return
``bytes`` (as ``redis.asyncio.Redis`` does by default when
``decode_responses=False``); the cache decodes UTF-8 itself rather than
silently breaking on a misconfigured deployer.

Production wiring (recommended):

    import redis.asyncio as redis
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    cache = CachedPolicyClient(opa_client, redis_client)

Either ``decode_responses=True`` or ``decode_responses=False`` works --
the cache handles both. The ``True`` setting is preferred because it
lets logs and stats inspectors see strings directly.

Public API:
  - ``CACHE_TTL_SECONDS``  the 5-second default
  - ``CACHE_KEY_PREFIX``   ``verixa:policy``
  - ``RedisLike``          Protocol describing the minimum interface
  - ``CachedPolicyClient`` the wrapper
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Final, Protocol

from verixa_runtime.policy.client import (
    OpaPolicyClient,
    PolicyClientError,
    PolicyDecision,
    PolicyDecisionKind,
)

CACHE_TTL_SECONDS: Final[int] = 5
CACHE_KEY_PREFIX: Final[str] = "verixa:policy"


class RedisLike(Protocol):  # pragma: no cover
    """Minimum async interface the cache needs.

    Compatible with ``redis.asyncio.Redis`` (production) and
    ``InMemoryRedisStub`` (tests). Method bodies are typing stubs;
    they are excluded from coverage because they never execute --
    the actual implementations live in production redis.asyncio
    or in the test stub.
    """

    async def get(self, key: str) -> str | bytes | None: ...

    async def setex(
        self, key: str, ttl_seconds: int, value: str
    ) -> None: ...


def _canonical_input_hash(input_doc: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON of input_doc -- deterministic + key-stable."""
    payload = json.dumps(
        input_doc, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _build_cache_key(
    tenant_id: uuid.UUID, package: str, input_doc: dict[str, Any]
) -> str:
    return (
        f"{CACHE_KEY_PREFIX}:{tenant_id}:{package}:"
        f"{_canonical_input_hash(input_doc)}"
    )


def _serialise_decision(decision: PolicyDecision) -> str:
    return json.dumps(
        {
            "decision": decision.decision.value,
            "reason": decision.reason,
            "raw": decision.raw,
        },
        separators=(",", ":"),
    )


def _coerce_payload_to_str(payload: str | bytes) -> str:
    """Accept the str-or-bytes return of redis.get; decode UTF-8 if bytes.

    Falls through with ``PolicyClientError`` if the bytes aren't valid
    UTF-8 -- this should never happen for our own writes (we always
    write str-encoded JSON) but defends against a poisoned cache or a
    cache key collision with another writer.
    """
    if isinstance(payload, bytes):
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError as e:
            raise PolicyClientError(
                f"cache payload is not valid UTF-8: {e}"
            ) from e
    return payload


def _deserialise_decision(payload: str | bytes) -> PolicyDecision:
    """Reverse of `_serialise_decision`. Raises PolicyClientError on bad cache.

    Accepts both ``str`` and ``bytes`` payloads to tolerate
    ``redis.asyncio`` deployments where ``decode_responses=False``.
    """
    text = _coerce_payload_to_str(payload)
    try:
        body = json.loads(text)
    except json.JSONDecodeError as e:
        raise PolicyClientError(f"corrupt cache payload: {e}") from e
    if not isinstance(body, dict):
        raise PolicyClientError("cache payload is not a JSON object")
    for required in ("decision", "reason"):
        if required not in body:
            raise PolicyClientError(
                f"cache payload missing field {required!r}"
            )
    try:
        kind = PolicyDecisionKind(body["decision"])
    except ValueError as e:
        raise PolicyClientError(
            f"cache payload has invalid decision {body['decision']!r}"
        ) from e
    raw = body.get("raw", {})
    if not isinstance(raw, dict):
        raise PolicyClientError("cache payload 'raw' is not an object")
    return PolicyDecision(decision=kind, reason=str(body["reason"]), raw=raw)


@dataclass(frozen=True, slots=True)
class CacheStats:
    """Hit/miss counters returned by ``CachedPolicyClient.stats``."""

    hits: int
    misses: int


class CachedPolicyClient:
    """Cache-on-read wrapper around an ``OpaPolicyClient``.

    Cache miss policy:
      1. Look up cache key.
      2. If hit: deserialise + return.
      3. If miss: call OPA, write result with TTL, return.

    Cache write policy: only successful evaluations are cached.
    ``PolicyClientError``s propagate uncached so transient OPA failures
    don't poison the cache.
    """

    def __init__(
        self,
        opa_client: OpaPolicyClient,
        redis: RedisLike,
        *,
        ttl_seconds: int = CACHE_TTL_SECONDS,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._opa = opa_client
        self._redis = redis
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    @property
    def stats(self) -> CacheStats:
        return CacheStats(hits=self._hits, misses=self._misses)

    async def evaluate(
        self,
        tenant_id: uuid.UUID,
        package: str,
        input_doc: dict[str, Any],
    ) -> PolicyDecision:
        """Cache-aware decision evaluation."""
        if not isinstance(tenant_id, uuid.UUID):
            raise ValueError(
                f"tenant_id must be uuid.UUID, got {type(tenant_id).__name__}"
            )
        cache_key = _build_cache_key(tenant_id, package, input_doc)
        cached = await self._redis.get(cache_key)
        if cached is not None:
            self._hits += 1
            return _deserialise_decision(cached)
        self._misses += 1
        decision = await self._opa.evaluate(package, input_doc)
        await self._redis.setex(
            cache_key, self._ttl_seconds, _serialise_decision(decision)
        )
        return decision
