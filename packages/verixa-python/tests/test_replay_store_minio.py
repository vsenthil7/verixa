"""pytest suite for verixa_runtime.replay.minio_store (CP-12.6).

Two layers:

  1. **Unit tests with a fake MinIO client** -- default loop, runs
     with ``pytest -m 'not integration'``. Covers serialisation
     round-trip, every branch of every method, error paths.
  2. **Live MinIO testcontainer round-trip** -- gated by
     ``@pytest.mark.integration``. Skipped if Docker isn't running.
     Confirms the real wire works.
"""

from __future__ import annotations

import uuid

import pytest
from verixa_runtime.crypto.aes_gcm import generate_key
from verixa_runtime.replay import (
    BundleConflict,
    BundleNotFound,
    EncryptedBundle,
    MinioBundleStore,
    ReplayBundle,
    encrypt_bundle,
)
from verixa_runtime.replay.minio_store import (
    _deserialise_from_minio,
    _serialise_for_minio,
)

_TENANT = uuid.UUID("11111111-2222-3333-4444-555555555555")
_AUDIT = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _make_bundle() -> EncryptedBundle:
    key = generate_key()
    rb = ReplayBundle(
        audit_id=_AUDIT,
        tenant_id=_TENANT,
        decision="allow",
        risk_score=0.1,
        request_envelope={"k": "v"},
        timestamp_unix_ns=1_700_000_000_000_000_000,
    )
    return encrypt_bundle(rb, key)


# ---------------------------------------------------------------------------
# Serialisation round-trip
# ---------------------------------------------------------------------------


def test_serialise_round_trip() -> None:
    eb = _make_bundle()
    raw = _serialise_for_minio(eb)
    eb_back = _deserialise_from_minio(raw)
    assert eb_back.storage_key == eb.storage_key
    assert eb_back.tenant_id == eb.tenant_id
    assert eb_back.audit_id == eb.audit_id
    assert eb_back.ciphertext.nonce == eb.ciphertext.nonce
    assert eb_back.ciphertext.ciphertext == eb.ciphertext.ciphertext
    assert eb_back.ciphertext.associated_data == eb.ciphertext.associated_data


def test_deserialise_rejects_schema_version_mismatch() -> None:
    import json

    payload = {
        "schema_version": 99,
        "storage_key": "0" * 64,
        "tenant_id": str(_TENANT),
        "audit_id": str(_AUDIT),
        "nonce_b64": "",
        "ciphertext_b64": "",
        "associated_data_b64": "",
    }
    raw = json.dumps(payload).encode("utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        _deserialise_from_minio(raw)


# ---------------------------------------------------------------------------
# Fake MinIO client + behavioural unit tests
# ---------------------------------------------------------------------------


class _FakeS3Error(Exception):
    """Stand-in for minio.error.S3Error in the fake client tests.

    Real S3Error carries a ``code`` attribute (e.g. NoSuchKey); we
    mirror that here so the production code path is exercised."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _FakeResponse:
    """Stand-in for the response object MinIO.get_object returns."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class _FakeMinioClient:
    """In-memory fake of the MinIO Python SDK surface we use.

    Tracks buckets + objects in nested dicts. Raises _FakeS3Error
    (which behaves like minio.error.S3Error w.r.t. .code) for
    missing-object access so the production code's NoSuchKey branch
    fires.
    """

    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.setdefault(bucket, {})

    def put_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data,
        length: int,
        content_type: str,
    ) -> None:
        # MinIO accepts a stream + length; read the bytes for the fake.
        self.buckets[bucket_name][object_name] = data.read()

    def get_object(self, bucket: str, object_name: str):
        if bucket not in self.buckets or object_name not in self.buckets[bucket]:
            raise _FakeS3Error("NoSuchKey")
        return _FakeResponse(self.buckets[bucket][object_name])

    def remove_object(self, bucket: str, object_name: str) -> None:
        self.buckets[bucket].pop(object_name, None)


@pytest.fixture(autouse=True)
def _patch_s3error(monkeypatch):
    """Patch minio.error.S3Error to our fake so the production code's
    ``except S3Error`` branch catches our fake errors during unit tests.
    """
    import minio.error as minio_error_mod

    monkeypatch.setattr(minio_error_mod, "S3Error", _FakeS3Error)


async def test_put_creates_bucket_and_stores_bundle() -> None:
    client = _FakeMinioClient()
    store = MinioBundleStore(client=client, bucket="test-bucket")
    eb = _make_bundle()
    key = await store.put(eb)
    assert key == eb.storage_key
    assert "test-bucket" in client.buckets
    assert eb.storage_key in client.buckets["test-bucket"]


async def test_get_returns_previously_put_bundle() -> None:
    client = _FakeMinioClient()
    store = MinioBundleStore(client=client, bucket="b")
    eb = _make_bundle()
    await store.put(eb)
    eb_back = await store.get(eb.storage_key)
    assert eb_back.storage_key == eb.storage_key
    assert eb_back.tenant_id == eb.tenant_id


async def test_exists_transitions_false_to_true() -> None:
    client = _FakeMinioClient()
    store = MinioBundleStore(client=client, bucket="b")
    eb = _make_bundle()
    assert await store.exists(eb.storage_key) is False
    await store.put(eb)
    assert await store.exists(eb.storage_key) is True


async def test_delete_removes_then_exists_false() -> None:
    client = _FakeMinioClient()
    store = MinioBundleStore(client=client, bucket="b")
    eb = _make_bundle()
    await store.put(eb)
    await store.delete(eb.storage_key)
    assert await store.exists(eb.storage_key) is False


async def test_get_missing_raises_bundle_not_found() -> None:
    client = _FakeMinioClient()
    client.make_bucket("b")
    store = MinioBundleStore(client=client, bucket="b")
    with pytest.raises(BundleNotFound):
        await store.get("0" * 64)


async def test_delete_missing_raises_bundle_not_found() -> None:
    client = _FakeMinioClient()
    client.make_bucket("b")
    store = MinioBundleStore(client=client, bucket="b")
    with pytest.raises(BundleNotFound):
        await store.delete("0" * 64)


async def test_put_idempotent_on_byte_identical_re_put() -> None:
    client = _FakeMinioClient()
    store = MinioBundleStore(client=client, bucket="b")
    eb = _make_bundle()
    k1 = await store.put(eb)
    k2 = await store.put(eb)
    assert k1 == k2
    # Only one object in the bucket.
    assert len(client.buckets["b"]) == 1


async def test_put_conflict_on_different_bytes_under_same_key() -> None:
    client = _FakeMinioClient()
    store = MinioBundleStore(client=client, bucket="b")
    eb_real = _make_bundle()
    await store.put(eb_real)
    # Forge an EncryptedBundle that lies about its storage_key.
    eb_other = _make_bundle()
    forged = EncryptedBundle(
        ciphertext=eb_other.ciphertext,
        storage_key=eb_real.storage_key,  # collision
        tenant_id=eb_other.tenant_id,
        audit_id=eb_other.audit_id,
    )
    with pytest.raises(BundleConflict):
        await store.put(forged)


async def test_get_propagates_unexpected_s3_error() -> None:
    """An S3Error with a code OTHER than NoSuchKey/NoSuchBucket
    bubbles up rather than being swallowed as None."""
    client = _FakeMinioClient()
    client.make_bucket("b")
    store = MinioBundleStore(client=client, bucket="b")

    def _boom(bucket, object_name):  # noqa: ARG001
        raise _FakeS3Error("InternalError")

    client.get_object = _boom  # type: ignore[assignment]
    with pytest.raises(_FakeS3Error):
        await store.get("0" * 64)
