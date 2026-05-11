"""MinIO-backed BundleStore (CP-12.6).

Production-grade BundleStore implementation using the MinIO Python
SDK (works against any S3-compatible object store: MinIO, AWS S3,
Cloudflare R2, Backblaze B2). The serialised on-disk shape is a
small JSON wrapper carrying the AesGcmCiphertext's nonce + ciphertext
+ associated_data plus the storage_key + tenant_id + audit_id labels;
each EncryptedBundle becomes one object whose key is the
content-addressable storage_key.

The MinIO client is synchronous; this implementation wraps every
call in ``asyncio.to_thread`` so it satisfies the async
``BundleStore`` Protocol without blocking the event loop.

Tests for this module live in test_replay_store_minio.py and are
gated behind ``@pytest.mark.integration`` -- they spin up a MinIO
container via testcontainers. The default ``pytest -m 'not
integration'`` loop skips them.

Bucket model: one bucket per environment (e.g. ``verixa-replay-dev``).
All tenants share the bucket; per-tenant isolation comes from the
AES key (the ciphertext is opaque to MinIO). When a key is rotated
or zeroised, the ciphertext bytes stay in MinIO as audit artefacts
but are unrecoverable -- this is the GDPR Article 17 cryptographic
erasure path documented in store.py.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from typing import Final

from verixa_runtime.crypto.aes_gcm import AesGcmCiphertext
from verixa_runtime.replay.sealer import EncryptedBundle
from verixa_runtime.replay.store import BundleConflict, BundleNotFound

# On-disk wire format version; bumped when the JSON shape changes
# incompatibly. The MinIO object body is JSON, the bytes inside are
# base64-encoded.
_MINIO_OBJECT_SCHEMA_VERSION: Final[int] = 1


def _serialise_for_minio(bundle: EncryptedBundle) -> bytes:
    """Encode an EncryptedBundle into bytes for MinIO upload.

    Format: JSON object with base64-encoded ciphertext fields plus
    the storage_key + tenant_id + audit_id labels. Round-trips
    cleanly with _deserialise_from_minio.
    """
    payload = {
        "schema_version": _MINIO_OBJECT_SCHEMA_VERSION,
        "storage_key": bundle.storage_key,
        "tenant_id": str(bundle.tenant_id),
        "audit_id": str(bundle.audit_id),
        "nonce_b64": base64.b64encode(bundle.ciphertext.nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(
            bundle.ciphertext.ciphertext
        ).decode("ascii"),
        "associated_data_b64": base64.b64encode(
            bundle.ciphertext.associated_data
        ).decode("ascii"),
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _deserialise_from_minio(data: bytes) -> EncryptedBundle:
    """Inverse of _serialise_for_minio."""
    import uuid as uuid_mod

    payload = json.loads(data.decode("utf-8"))
    if payload.get("schema_version") != _MINIO_OBJECT_SCHEMA_VERSION:
        raise ValueError(
            f"MinIO object schema_version mismatch; expected "
            f"{_MINIO_OBJECT_SCHEMA_VERSION}, got "
            f"{payload.get('schema_version')!r}"
        )
    ciphertext = AesGcmCiphertext(
        nonce=base64.b64decode(payload["nonce_b64"]),
        ciphertext=base64.b64decode(payload["ciphertext_b64"]),
        associated_data=base64.b64decode(payload["associated_data_b64"]),
    )
    return EncryptedBundle(
        ciphertext=ciphertext,
        storage_key=payload["storage_key"],
        tenant_id=uuid_mod.UUID(payload["tenant_id"]),
        audit_id=uuid_mod.UUID(payload["audit_id"]),
    )


class MinioBundleStore:
    """Async BundleStore backed by a real S3-compatible MinIO bucket.

    Construction signature mirrors InMemoryBundleStore so call-sites
    can swap implementations without other changes. The ``client``
    parameter is a MinIO client; the ``bucket`` is the target
    bucket name (created on first put if absent).
    """

    def __init__(self, *, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def _ensure_bucket(self) -> None:
        def _check() -> None:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)

        await asyncio.to_thread(_check)

    async def put(self, bundle: EncryptedBundle) -> str:
        await self._ensure_bucket()
        body = _serialise_for_minio(bundle)

        # Idempotent re-put: if an object with this storage_key already
        # exists and the bytes are byte-identical, return without
        # rewriting. If bytes differ, raise BundleConflict (matches
        # InMemoryBundleStore semantics).
        existing = await self._get_bytes_or_none(bundle.storage_key)
        if existing is not None:
            if existing == body:
                return bundle.storage_key
            raise BundleConflict(
                f"storage_key {bundle.storage_key!r} already exists "
                f"in bucket {self._bucket!r} with different bytes"
            )

        def _upload() -> None:
            self._client.put_object(
                bucket_name=self._bucket,
                object_name=bundle.storage_key,
                data=io.BytesIO(body),
                length=len(body),
                content_type="application/json",
            )

        await asyncio.to_thread(_upload)
        return bundle.storage_key

    async def get(self, storage_key: str) -> EncryptedBundle:
        data = await self._get_bytes_or_none(storage_key)
        if data is None:
            raise BundleNotFound(
                f"no bundle at storage_key={storage_key!r} in "
                f"bucket {self._bucket!r}"
            )
        return _deserialise_from_minio(data)

    async def exists(self, storage_key: str) -> bool:
        return (
            await self._get_bytes_or_none(storage_key)
        ) is not None

    async def delete(self, storage_key: str) -> None:
        # Check existence first so we can raise BundleNotFound on
        # missing keys (matches InMemoryBundleStore semantics; MinIO's
        # remove_object is silent on missing).
        if not await self.exists(storage_key):
            raise BundleNotFound(
                f"no bundle at storage_key={storage_key!r} in "
                f"bucket {self._bucket!r}"
            )

        def _remove() -> None:
            self._client.remove_object(self._bucket, storage_key)

        await asyncio.to_thread(_remove)

    async def _get_bytes_or_none(self, storage_key: str) -> bytes | None:
        """Fetch object bytes, or None if the object doesn't exist."""
        from minio.error import S3Error

        def _fetch() -> bytes | None:
            try:
                response = self._client.get_object(self._bucket, storage_key)
                try:
                    return response.read()
                finally:
                    response.close()
                    response.release_conn()
            except S3Error as e:
                # NoSuchKey is the documented missing-object code.
                if e.code in ("NoSuchKey", "NoSuchBucket"):
                    return None
                raise

        return await asyncio.to_thread(_fetch)


__all__ = [
    "MinioBundleStore",
]
