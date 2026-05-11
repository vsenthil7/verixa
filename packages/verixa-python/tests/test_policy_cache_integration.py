"""Live Redis integration tests for CachedPolicyClient (CP-8.6).

These tests spin up a real Redis container via testcontainers and run
the cache against ``redis.asyncio.Redis``. They cover what the in-memory
stub cannot:

  - Real ``redis.asyncio.Redis.get`` returning ``bytes`` (when
    ``decode_responses=False``) and ``str`` (when ``decode_responses=True``)
  - Real ``setex`` TTL expiry
  - Wire-level encoding: bytes round-trip through redis-server

These tests are opt-in via the ``integration`` pytest marker and skip
cleanly when Docker isn't available so the default test suite stays
fast and Docker-free.

To run locally:
  poetry run pytest -m integration packages/verixa-python/tests/test_policy_cache_integration.py -v
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import pytest

# These imports are deferred at module-import time -- the ``integration``
# marker may run on machines without Docker, in which case the test
# class is skipped before ever touching testcontainers.
testcontainers = pytest.importorskip("testcontainers.redis")
redis_asyncio = pytest.importorskip("redis.asyncio")
RedisContainer = testcontainers.RedisContainer  # type: ignore[attr-defined]

from verixa_runtime.policy import client as client_module
from verixa_runtime.policy.cache import CachedPolicyClient, CacheStats
from verixa_runtime.policy.client import (
    OpaPolicyClient,
    PolicyDecisionKind,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa42")


# ---------------------------------------------------------------------------
# Docker-availability gate
# ---------------------------------------------------------------------------


def _docker_is_running() -> bool:
    """Return True iff a Docker daemon responds to a basic call."""
    try:
        import docker  # type: ignore

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


# Skip the entire module on machines without Docker -- the in-memory
# cache tests still cover the deterministic logic; this file's job is
# to catch the bugs that ONLY surface against real Redis.
if not _docker_is_running():
    pytest.skip(
        "Docker daemon not available; skipping live Redis integration tests",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def redis_container():
    """Module-scoped Redis container -- one container per test module."""
    container = RedisContainer("redis:7-alpine")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture
async def redis_str_client(redis_container):
    """redis.asyncio.Redis with decode_responses=True (recommended Verixa default)."""
    host = redis_container.get_container_host_ip()
    port = int(redis_container.get_exposed_port(6379))
    client = redis_asyncio.Redis(
        host=host, port=port, decode_responses=True
    )
    # Wipe any leftover state between tests
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def redis_bytes_client(redis_container):
    """redis.asyncio.Redis with decode_responses=False -- the foot-gun config."""
    host = redis_container.get_container_host_ip()
    port = int(redis_container.get_exposed_port(6379))
    client = redis_asyncio.Redis(
        host=host, port=port, decode_responses=False
    )
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()


def _build_opa_with_handler(
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
# Live Redis tests -- these are the coverage gaps the stub couldn't fill
# ---------------------------------------------------------------------------


async def test_live_redis_with_decode_responses_true(
    redis_str_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recommended Verixa wiring: get returns str."""
    call_count: list[int] = []
    opa = _build_opa_with_handler(monkeypatch, _opa_pass_handler(call_count))
    cache = CachedPolicyClient(opa, redis_str_client)

    input_doc = {"action": {"tool_name": "transfer"}}
    d1 = await cache.evaluate(TENANT, "verixa.fs.x", input_doc)
    d2 = await cache.evaluate(TENANT, "verixa.fs.x", input_doc)

    assert d1.decision == PolicyDecisionKind.PASS
    assert d2.decision == PolicyDecisionKind.PASS
    assert len(call_count) == 1  # only one OPA round-trip
    assert cache.stats == CacheStats(hits=1, misses=1)


async def test_live_redis_with_decode_responses_false(
    redis_bytes_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Foot-gun config: get returns bytes. The cache must decode UTF-8
    transparently so a mis-configured deployer doesn't get a silent crash."""
    call_count: list[int] = []
    opa = _build_opa_with_handler(monkeypatch, _opa_pass_handler(call_count))
    cache = CachedPolicyClient(opa, redis_bytes_client)

    input_doc = {"action": {"tool_name": "transfer"}}
    await cache.evaluate(TENANT, "verixa.fs.x", input_doc)
    d2 = await cache.evaluate(TENANT, "verixa.fs.x", input_doc)

    assert d2.decision == PolicyDecisionKind.PASS
    assert len(call_count) == 1
    assert cache.stats == CacheStats(hits=1, misses=1)


async def test_live_redis_ttl_actually_expires(
    redis_str_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 5-second cache TTL is enforced by real Redis. After expiry,
    next call MUST hit OPA again. Uses a 1-second TTL to keep the test
    fast (the 5s production TTL is configurable; we exercise the same
    code path with a smaller value)."""
    call_count: list[int] = []
    opa = _build_opa_with_handler(monkeypatch, _opa_pass_handler(call_count))
    cache = CachedPolicyClient(opa, redis_str_client, ttl_seconds=1)

    input_doc = {"y": 1}
    await cache.evaluate(TENANT, "verixa.fs.x", input_doc)
    # Within TTL: cache hit
    await cache.evaluate(TENANT, "verixa.fs.x", input_doc)
    assert len(call_count) == 1

    # Wait for expiry plus a small margin
    await asyncio.sleep(1.5)

    # After TTL: must miss + re-call OPA
    await cache.evaluate(TENANT, "verixa.fs.x", input_doc)
    assert len(call_count) == 2
    assert cache.stats == CacheStats(hits=1, misses=2)


async def test_live_redis_no_cross_tenant_leak(
    redis_str_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two tenants with identical input must produce two distinct cache
    entries. Verifies the per-tenant key namespacing on the wire."""
    call_count: list[int] = []
    opa = _build_opa_with_handler(monkeypatch, _opa_pass_handler(call_count))
    cache = CachedPolicyClient(opa, redis_str_client)

    tenant_a = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa01")
    tenant_b = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa02")
    input_doc: dict[str, Any] = {"y": 1}

    await cache.evaluate(tenant_a, "verixa.fs.x", input_doc)
    await cache.evaluate(tenant_b, "verixa.fs.x", input_doc)

    assert len(call_count) == 2
    # And both entries actually live in Redis
    keys = await redis_str_client.keys("verixa:policy:*")
    assert len(keys) == 2


async def test_live_redis_corrupt_payload_raises_clean_error(
    redis_str_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If something else writes garbage at our cache key (e.g. a key
    collision with another writer), evaluate() must raise PolicyClientError
    rather than crash with a low-level decoding error."""
    from verixa_runtime.policy.cache import _build_cache_key
    from verixa_runtime.policy.client import PolicyClientError

    call_count: list[int] = []
    opa = _build_opa_with_handler(monkeypatch, _opa_pass_handler(call_count))
    cache = CachedPolicyClient(opa, redis_str_client)

    input_doc = {"y": 1}
    cache_key = _build_cache_key(TENANT, "verixa.fs.x", input_doc)
    # Plant garbage with a 60s TTL
    await redis_str_client.setex(cache_key, 60, "not even json")

    with pytest.raises(PolicyClientError, match="corrupt cache"):
        await cache.evaluate(TENANT, "verixa.fs.x", input_doc)
    # OPA was NOT called (the cache hit path raised before falling through)
    assert call_count == []
