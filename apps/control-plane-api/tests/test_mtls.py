"""CP-53 tests for verixa_control_plane.mtls -- ADR-0007 scaffold.

Phase-1 carry-forward "mTLS internal service mesh". Tests the typed
surface + reference InMemoryCertificateIssuer. The Vault-backed
implementation is Phase-1+ work; this file proves the Protocol shape
+ identity validation + issuance semantics are correct first.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from verixa_control_plane.mtls import (
    CertificateExpired,
    CertificateIssuer,
    CertificateRevoked,
    CertificateUnknown,
    InMemoryCertificateIssuer,
    IssuedCertificate,
    MtlsError,
    ServiceIdentity,
    ServiceIdentityInvalid,
    ServiceRole,
)

# ---------------------------------------------------------------------------
# ServiceRole enum
# ---------------------------------------------------------------------------


def test_service_role_has_four_known_roles() -> None:
    assert {r.value for r in ServiceRole} == {
        "runtime-gateway",
        "control-plane-api",
        "triad-worker",
        "opa-bundle-server",
    }


# ---------------------------------------------------------------------------
# ServiceIdentity.parse -- positive cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri,env,role,instance",
    [
        (
            "spiffe://verixa.local/prod/runtime-gateway/pod-abc123",
            "prod",
            ServiceRole.RUNTIME_GATEWAY,
            "pod-abc123",
        ),
        (
            "spiffe://verixa.local/dev/control-plane-api/local-dev",
            "dev",
            ServiceRole.CONTROL_PLANE_API,
            "local-dev",
        ),
        (
            "spiffe://verixa.local/staging/triad-worker/worker-0",
            "staging",
            ServiceRole.TRIAD_WORKER,
            "worker-0",
        ),
        (
            "spiffe://verixa.local/prod/opa-bundle-server/server-eu-west-1a",
            "prod",
            ServiceRole.OPA_BUNDLE_SERVER,
            "server-eu-west-1a",
        ),
    ],
)
def test_service_identity_parses_valid_uri(
    uri: str, env: str, role: ServiceRole, instance: str
) -> None:
    sid = ServiceIdentity.parse(uri)
    assert sid.spiffe_uri == uri
    assert sid.env == env
    assert sid.role is role
    assert sid.instance_id == instance


# ---------------------------------------------------------------------------
# ServiceIdentity.parse -- negative cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "",
        "spiffe://other.local/prod/runtime-gateway/pod-1",  # wrong trust domain
        "spiffe://verixa.local/prod/runtime-gateway/",  # empty instance
        "spiffe://verixa.local/prod//pod-1",  # empty role
        "spiffe://verixa.local//runtime-gateway/pod-1",  # empty env
        "spiffe://verixa.local/PROD/runtime-gateway/pod-1",  # uppercase env
        "spiffe://verixa.local/prod/UNKNOWN-ROLE/pod-1",  # role not in enum
        "spiffe://verixa.local/prod/runtime-gateway/pod with space",
        "http://verixa.local/prod/runtime-gateway/pod-1",  # wrong scheme
        "spiffe://verixa.local/prod/runtime-gateway",  # missing instance segment
    ],
)
def test_service_identity_rejects_invalid_uri(uri: str) -> None:
    with pytest.raises(ServiceIdentityInvalid):
        ServiceIdentity.parse(uri)


def test_service_identity_rejects_unknown_env() -> None:
    """env 'production' is not in the allowlist {dev,staging,prod}."""
    with pytest.raises(ServiceIdentityInvalid, match="allowlist"):
        ServiceIdentity.parse(
            "spiffe://verixa.local/production/runtime-gateway/pod-1"
        )


def test_service_identity_rejects_non_string() -> None:
    with pytest.raises(ServiceIdentityInvalid, match="must be str"):
        ServiceIdentity.parse(None)  # type: ignore[arg-type]
    with pytest.raises(ServiceIdentityInvalid, match="must be str"):
        ServiceIdentity.parse(b"spiffe://verixa.local/prod/x/y")  # type: ignore[arg-type]


def test_service_identity_rejects_lowercase_unknown_role() -> None:
    """The regex allows any lowercase 3-32-char role string, so unknown
    roles must be caught by the ServiceRole enum check. Tests the
    enum-rejection branch (vs regex-rejection which catches uppercase)."""
    with pytest.raises(ServiceIdentityInvalid, match="not in ServiceRole enum"):
        ServiceIdentity.parse(
            "spiffe://verixa.local/prod/some-future-role/pod-1"
        )


# ---------------------------------------------------------------------------
# IssuedCertificate validation
# ---------------------------------------------------------------------------


def _identity() -> ServiceIdentity:
    return ServiceIdentity.parse(
        "spiffe://verixa.local/prod/runtime-gateway/pod-abc"
    )


def test_issued_certificate_rejects_inverted_validity_window() -> None:
    now = datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC)
    with pytest.raises(MtlsError, match="must be after"):
        IssuedCertificate(
            cert_id=uuid.uuid4(),
            identity=_identity(),
            pem_bytes=b"...",
            issuer_id="verixa-mtls-test",
            not_before=now,
            not_after=now - timedelta(hours=1),
            serial=1,
        )


def test_issued_certificate_rejects_zero_window() -> None:
    now = datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC)
    with pytest.raises(MtlsError, match="must be after"):
        IssuedCertificate(
            cert_id=uuid.uuid4(),
            identity=_identity(),
            pem_bytes=b"...",
            issuer_id="x",
            not_before=now,
            not_after=now,
            serial=1,
        )


def test_issued_certificate_rejects_negative_serial() -> None:
    now = datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC)
    with pytest.raises(MtlsError, match="serial"):
        IssuedCertificate(
            cert_id=uuid.uuid4(),
            identity=_identity(),
            pem_bytes=b"...",
            issuer_id="x",
            not_before=now,
            not_after=now + timedelta(hours=1),
            serial=-1,
        )


def test_issued_certificate_is_expired_after_not_after() -> None:
    now = datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC)
    cert = IssuedCertificate(
        cert_id=uuid.uuid4(),
        identity=_identity(),
        pem_bytes=b"...",
        issuer_id="x",
        not_before=now,
        not_after=now + timedelta(hours=1),
        serial=1,
    )
    assert cert.is_expired(now=now + timedelta(minutes=30)) is False
    assert cert.is_expired(now=now + timedelta(hours=2)) is True


def test_issued_certificate_needs_renewal_within_lead_time() -> None:
    now = datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC)
    cert = IssuedCertificate(
        cert_id=uuid.uuid4(),
        identity=_identity(),
        pem_bytes=b"...",
        issuer_id="x",
        not_before=now,
        not_after=now + timedelta(hours=2),
        serial=1,
    )
    # 30 min in -- not yet within 1h lead time
    assert cert.needs_renewal(now=now + timedelta(minutes=30)) is False
    # 90 min in -- now within 1h lead time
    assert cert.needs_renewal(now=now + timedelta(minutes=90)) is True


def test_issued_certificate_needs_renewal_custom_lead_time() -> None:
    now = datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC)
    cert = IssuedCertificate(
        cert_id=uuid.uuid4(),
        identity=_identity(),
        pem_bytes=b"...",
        issuer_id="x",
        not_before=now,
        not_after=now + timedelta(hours=24),
        serial=1,
    )
    # 30 min in, 6h lead time -- not within window
    assert (
        cert.needs_renewal(
            now=now + timedelta(minutes=30), lead_time=timedelta(hours=6)
        )
        is False
    )
    # 20h in, 6h lead time -- within window
    assert (
        cert.needs_renewal(
            now=now + timedelta(hours=20), lead_time=timedelta(hours=6)
        )
        is True
    )


def test_issued_certificate_defaults_now_to_utc_now() -> None:
    """is_expired/needs_renewal without now= use datetime.now(UTC)."""
    now = datetime.now(UTC)
    cert = IssuedCertificate(
        cert_id=uuid.uuid4(),
        identity=_identity(),
        pem_bytes=b"...",
        issuer_id="x",
        not_before=now - timedelta(hours=1),
        not_after=now + timedelta(hours=10),
        serial=1,
    )
    # Default-now path; cert is valid now -> not expired + not needing renewal
    assert cert.is_expired() is False
    assert cert.needs_renewal() is False


# ---------------------------------------------------------------------------
# InMemoryCertificateIssuer.issue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_creates_certificate_with_correct_identity() -> None:
    issuer = InMemoryCertificateIssuer()
    sid = _identity()
    cert = await issuer.issue(sid, ttl=timedelta(hours=24))
    assert cert.identity == sid
    assert cert.issuer_id == "verixa-mtls-inmemory"
    assert cert.serial == 1
    assert b"VERIXA-PLACEHOLDER-CERT-ID-" in cert.pem_bytes
    assert sid.spiffe_uri.encode("utf-8") in cert.pem_bytes


@pytest.mark.asyncio
async def test_issue_uses_custom_issuer_id() -> None:
    issuer = InMemoryCertificateIssuer(issuer_id="verixa-mtls-prod-vault")
    sid = _identity()
    cert = await issuer.issue(sid, ttl=timedelta(hours=1))
    assert cert.issuer_id == "verixa-mtls-prod-vault"
    assert issuer.issuer_id == "verixa-mtls-prod-vault"


@pytest.mark.asyncio
async def test_issue_assigns_monotonic_serials() -> None:
    issuer = InMemoryCertificateIssuer()
    sid = _identity()
    c1 = await issuer.issue(sid, ttl=timedelta(hours=1))
    c2 = await issuer.issue(sid, ttl=timedelta(hours=1))
    c3 = await issuer.issue(sid, ttl=timedelta(hours=1))
    assert (c1.serial, c2.serial, c3.serial) == (1, 2, 3)


@pytest.mark.asyncio
async def test_issue_rejects_zero_ttl() -> None:
    issuer = InMemoryCertificateIssuer()
    with pytest.raises(MtlsError, match="positive"):
        await issuer.issue(_identity(), ttl=timedelta(0))


@pytest.mark.asyncio
async def test_issue_rejects_negative_ttl() -> None:
    issuer = InMemoryCertificateIssuer()
    with pytest.raises(MtlsError, match="positive"):
        await issuer.issue(_identity(), ttl=timedelta(hours=-1))


@pytest.mark.asyncio
async def test_issue_rejects_ttl_over_90_days() -> None:
    """Verixa policy: leaf cert TTL capped at 90 days; typical is 24h."""
    issuer = InMemoryCertificateIssuer()
    with pytest.raises(MtlsError, match="90-day cap"):
        await issuer.issue(_identity(), ttl=timedelta(days=91))


@pytest.mark.asyncio
async def test_issue_accepts_exactly_90_day_ttl() -> None:
    """90 days exactly is allowed; 91 is rejected."""
    issuer = InMemoryCertificateIssuer()
    cert = await issuer.issue(_identity(), ttl=timedelta(days=90))
    assert cert.cert_id is not None


# ---------------------------------------------------------------------------
# InMemoryCertificateIssuer.verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_passes_for_fresh_cert() -> None:
    issuer = InMemoryCertificateIssuer()
    cert = await issuer.issue(_identity(), ttl=timedelta(hours=24))
    # No raise
    await issuer.verify(cert)


@pytest.mark.asyncio
async def test_verify_raises_for_expired_cert() -> None:
    issuer = InMemoryCertificateIssuer()
    cert = await issuer.issue(_identity(), ttl=timedelta(hours=1))
    future = datetime.now(UTC) + timedelta(hours=2)
    with pytest.raises(CertificateExpired):
        await issuer.verify(cert, now=future)


@pytest.mark.asyncio
async def test_verify_raises_for_revoked_cert() -> None:
    issuer = InMemoryCertificateIssuer()
    cert = await issuer.issue(_identity(), ttl=timedelta(hours=24))
    await issuer.revoke(cert.cert_id)
    with pytest.raises(CertificateRevoked):
        await issuer.verify(cert)


@pytest.mark.asyncio
async def test_verify_raises_for_unknown_cert() -> None:
    """A cert with a cert_id not in the issuer's records is rejected.
    Defends against forged-but-well-formed certs passed in by a caller."""
    issuer = InMemoryCertificateIssuer()
    sid = _identity()
    now = datetime.now(UTC)
    forged = IssuedCertificate(
        cert_id=uuid.uuid4(),
        identity=sid,
        pem_bytes=b"forged",
        issuer_id="verixa-mtls-inmemory",
        not_before=now,
        not_after=now + timedelta(hours=1),
        serial=999,
    )
    with pytest.raises(CertificateUnknown):
        await issuer.verify(forged)


# ---------------------------------------------------------------------------
# InMemoryCertificateIssuer.revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_unknown_cert_raises() -> None:
    issuer = InMemoryCertificateIssuer()
    with pytest.raises(CertificateUnknown, match="cannot revoke"):
        await issuer.revoke(uuid.uuid4())


@pytest.mark.asyncio
async def test_revoke_makes_subsequent_verify_fail() -> None:
    issuer = InMemoryCertificateIssuer()
    cert = await issuer.issue(_identity(), ttl=timedelta(hours=24))
    await issuer.verify(cert)  # passes before revocation
    await issuer.revoke(cert.cert_id)
    with pytest.raises(CertificateRevoked):
        await issuer.verify(cert)


@pytest.mark.asyncio
async def test_revoke_is_idempotent() -> None:
    """Revoking the same cert twice does not raise on the second call.

    The Phase-1+ Vault-backed implementation may want different semantics
    (e.g. record audit trail per revoke call); this Phase-0 reference
    keeps it simple."""
    issuer = InMemoryCertificateIssuer()
    cert = await issuer.issue(_identity(), ttl=timedelta(hours=24))
    await issuer.revoke(cert.cert_id)
    await issuer.revoke(cert.cert_id)
    with pytest.raises(CertificateRevoked):
        await issuer.verify(cert)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_in_memory_issuer_satisfies_protocol() -> None:
    """Structural subtype check: InMemoryCertificateIssuer IS a
    CertificateIssuer."""
    issuer: CertificateIssuer = InMemoryCertificateIssuer()
    assert hasattr(issuer, "issue")
    assert hasattr(issuer, "verify")
    assert hasattr(issuer, "revoke")
