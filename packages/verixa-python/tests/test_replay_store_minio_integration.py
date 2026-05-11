"""Live MinIO testcontainer integration test (CP-12.6).

Spins up a real MinIO container via testcontainers and runs a full
encrypt -> put -> get -> decrypt round-trip against it. Gated by
``@pytest.mark.integration`` so the default ``pytest -m 'not
integration'`` loop skips it.

Module-level Docker probe: if the docker daemon isn't reachable,
skip cleanly (mirrors the CP-8.6 Redis pattern). This way a
developer without Docker doesn't see red.
"""

from __future__ import annotations

import uuid

import pytest
from verixa_runtime.crypto.aes_gcm import generate_key
from verixa_runtime.replay import (
    BundleNotFound,
    MinioBundleStore,
    ReplayBundle,
    decrypt_bundle,
    encrypt_bundle,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Module-level Docker probe -- skip cleanly if unavailable
# ---------------------------------------------------------------------------


def _docker_is_up() -> bool:
    """Return True iff the local Docker daemon is reachable."""
    try:
        import docker  # noqa: PLC0415
    except ImportError:
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:  # noqa: BLE001
        return False


if not _docker_is_up():  # pragma: no cover -- depends on docker
    pytest.skip(
        "Docker daemon not available; skipping live MinIO integration tests",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Live MinIO container fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def minio_container():  # type: ignore[no-untyped-def]
    """Spin up a real MinIO container for the test module."""
    from testcontainers.minio import MinioContainer

    with MinioContainer() as mc:
        yield mc


@pytest.fixture
def minio_client(minio_container):  # type: ignore[no-untyped-def]
    """MinIO Python SDK client pointed at the test container."""
    from minio import Minio

    config = minio_container.get_config()
    return Minio(
        endpoint=config["endpoint"],
        access_key=config["access_key"],
        secret_key=config["secret_key"],
        secure=False,
    )


def _fresh_bundle() -> tuple:  # type: ignore[type-arg]
    key = generate_key()
    rb = ReplayBundle(
        audit_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        decision="allow",
        risk_score=0.1,
        request_envelope={"k": "v"},
        timestamp_unix_ns=1_700_000_000_000_000_000,
    )
    return encrypt_bundle(rb, key), key


# ---------------------------------------------------------------------------
# Live round-trip tests
# ---------------------------------------------------------------------------


async def test_live_minio_put_get_round_trip(minio_client) -> None:
    """The full happy path: put + get + decrypt against real MinIO."""
    store = MinioBundleStore(
        client=minio_client, bucket=f"test-bucket-{uuid.uuid4().hex[:8]}"
    )
    eb, key = _fresh_bundle()
    await store.put(eb)
    eb_back = await store.get(eb.storage_key)
    rb_back = decrypt_bundle(eb_back, key)
    assert rb_back.audit_id == eb.audit_id
    assert rb_back.decision == "allow"


async def test_live_minio_exists_and_delete(minio_client) -> None:
    """exists + delete cycle against real MinIO."""
    store = MinioBundleStore(
        client=minio_client, bucket=f"test-bucket-{uuid.uuid4().hex[:8]}"
    )
    eb, _ = _fresh_bundle()
    assert await store.exists(eb.storage_key) is False
    await store.put(eb)
    assert await store.exists(eb.storage_key) is True
    await store.delete(eb.storage_key)
    assert await store.exists(eb.storage_key) is False


async def test_live_minio_get_missing_raises_bundle_not_found(minio_client) -> None:
    """Missing key against real MinIO returns BundleNotFound, not a raw S3Error."""
    bucket = f"test-bucket-{uuid.uuid4().hex[:8]}"
    store = MinioBundleStore(client=minio_client, bucket=bucket)
    # Put something so the bucket exists, then ask for a different key.
    eb, _ = _fresh_bundle()
    await store.put(eb)
    with pytest.raises(BundleNotFound):
        await store.get("0" * 64)
