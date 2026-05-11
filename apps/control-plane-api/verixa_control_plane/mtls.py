"""CP-53 -- mTLS internal service mesh scaffold (ADR-0007 Phase-1 surface).

Closes the Phase-1 carry-forward "mTLS internal service mesh" item from
the rollup. This module defines the TYPED SURFACE for issuing + validating
per-service mTLS certificates used inside the Verixa runtime+control-plane
mesh. The actual PKI implementation -- HashiCorp Vault PKI engine + cert-
manager integration -- lands when ADR-0007 is approved and the persistence
swap (CP-Phase-1-multi-session) happens.

Service identity model (per ADR-0007 + BR-09 zero-trust between Verixa
components):

  spiffe://verixa.local/<env>/<role>/<instance-id>

  env       = dev / staging / prod
  role      = runtime-gateway / control-plane-api / triad-worker / opa-bundle-server
  instance  = stable identifier (Kubernetes pod name in production)

mTLS handshake protocol (defence-in-depth between Verixa services):

  1. Caller presents its leaf certificate (signed by Verixa Root CA)
  2. Receiver validates the cert chain to the Root CA
  3. Receiver extracts the SPIFFE URI from the cert's SAN
  4. Receiver checks role-vs-endpoint authorization (e.g. only the
     runtime-gateway role can POST /v1/internal/decisions)
  5. Receiver records the verified caller identity in the audit ledger

Phase-0 ships (this commit):

  - ServiceRole           enum (4 well-known roles)
  - ServiceIdentity       frozen dataclass: SPIFFE-URI + parsed fields
  - IssuedCertificate     frozen dataclass: PEM + identity + expiry
  - CertificateIssuer     Protocol: issue + verify_chain + revoke
  - InMemoryCertificateIssuer reference: stores identity-to-cert
    mapping; uses fake PEM bodies (the real implementation will use
    cryptography.x509 + Vault PKI). The Protocol surface is the
    immovable contract; the storage swap is Phase-1+ work.

Phase-1+ implementation:

  - VaultCertificateIssuer wrapping the Vault PKI transit engine
  - Cert rotation: 24h leaf TTL + 1-hour pre-expiry renewal triggers
  - CRL distribution + OCSP stapling for revoked-cert propagation
  - SPIFFE Workload API integration for automatic identity binding
  - Hardware TEE attestation gate (per ADR-0007 Phase-3 commitment)

Module is INFRASTRUCTURE-only: no I/O, no real crypto. The PEM bytes in
IssuedCertificate are opaque placeholders that the Vault-backed
implementation will replace with real X.509 chains. This keeps Phase-0
testing pure + the Vault-specific code isolated.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Final, Protocol


class ServiceRole(str, Enum):
    """Allowlist of well-known Verixa service roles.

    Adding a new role here is a deliberate authorization-surface change;
    it MUST be paired with an update to the authz matrix in the runtime
    gateway (Phase-1+).
    """

    RUNTIME_GATEWAY = "runtime-gateway"
    CONTROL_PLANE_API = "control-plane-api"
    TRIAD_WORKER = "triad-worker"
    OPA_BUNDLE_SERVER = "opa-bundle-server"


# SPIFFE-URI pattern: spiffe://verixa.local/<env>/<role>/<instance>
# Allowed chars in each segment: lowercase alphanumeric + hyphen.
# Length bounds prevent runaway inputs.
_SPIFFE_RE: Final = re.compile(
    r"^spiffe://verixa\.local/"
    r"(?P<env>[a-z0-9][a-z0-9-]{0,15})/"
    r"(?P<role>[a-z][a-z0-9-]{2,31})/"
    r"(?P<instance>[a-z0-9][a-z0-9-]{0,63})$"
)

# Allowed env values. Other envs are explicitly rejected -- production
# pipelines should not accidentally issue certs for unknown environments.
_ALLOWED_ENVS: Final[frozenset[str]] = frozenset({"dev", "staging", "prod"})


class MtlsError(RuntimeError):
    """Base for mTLS subsystem failures."""


class ServiceIdentityInvalid(MtlsError):
    """SPIFFE URI fails the allow-list pattern."""


class CertificateExpired(MtlsError):
    """The certificate's not_after has passed."""


class CertificateRevoked(MtlsError):
    """The certificate has been revoked by the issuer."""


class CertificateUnknown(MtlsError):
    """The certificate was never issued by this issuer."""


@dataclass(frozen=True, slots=True)
class ServiceIdentity:
    """A parsed SPIFFE identity for a Verixa service instance."""

    spiffe_uri: str
    env: str
    role: ServiceRole
    instance_id: str

    @classmethod
    def parse(cls, spiffe_uri: str) -> ServiceIdentity:
        """Parse + validate a SPIFFE URI into a ServiceIdentity.

        Raises ServiceIdentityInvalid if the URI fails the allow-list.
        """
        if not isinstance(spiffe_uri, str):
            raise ServiceIdentityInvalid(
                f"spiffe_uri must be str; got {type(spiffe_uri).__name__}"
            )
        m = _SPIFFE_RE.match(spiffe_uri)
        if m is None:
            raise ServiceIdentityInvalid(
                f"spiffe_uri {spiffe_uri!r} does not match required "
                f"pattern spiffe://verixa.local/<env>/<role>/<instance>"
            )
        env = m.group("env")
        role_str = m.group("role")
        instance = m.group("instance")
        if env not in _ALLOWED_ENVS:
            raise ServiceIdentityInvalid(
                f"env {env!r} not in allowlist {sorted(_ALLOWED_ENVS)}"
            )
        try:
            role = ServiceRole(role_str)
        except ValueError as e:
            raise ServiceIdentityInvalid(
                f"role {role_str!r} not in ServiceRole enum"
            ) from e
        return cls(
            spiffe_uri=spiffe_uri,
            env=env,
            role=role,
            instance_id=instance,
        )


@dataclass(frozen=True, slots=True)
class IssuedCertificate:
    """A leaf certificate issued for a service identity.

    The pem_bytes field holds the certificate body. Phase-0 reference
    implementation uses opaque placeholder bytes (the contract is the
    Protocol, not the bytes); Phase-1+ VaultCertificateIssuer puts real
    X.509 PEM here. The issuer_id binds the cert to the issuer instance
    that minted it -- enables key-rotation auditing.
    """

    cert_id: uuid.UUID
    identity: ServiceIdentity
    pem_bytes: bytes
    issuer_id: str
    not_before: datetime
    not_after: datetime
    serial: int

    def __post_init__(self) -> None:
        if self.not_after <= self.not_before:
            raise MtlsError(
                f"not_after {self.not_after.isoformat()} must be after "
                f"not_before {self.not_before.isoformat()}"
            )
        if self.serial < 0:
            raise MtlsError(f"serial must be >= 0; got {self.serial}")

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Return True iff now > not_after."""
        ts = now or datetime.now(UTC)
        return ts > self.not_after

    def needs_renewal(
        self, *, now: datetime | None = None, lead_time: timedelta | None = None
    ) -> bool:
        """Return True iff cert is within `lead_time` of expiry.

        Default lead_time = 1 hour, matching ADR-0007 renewal policy.
        """
        ts = now or datetime.now(UTC)
        lead = lead_time or timedelta(hours=1)
        return ts + lead >= self.not_after


class CertificateIssuer(Protocol):
    """Surface for issuing + verifying per-service mTLS certificates.

    Phase-0: InMemoryCertificateIssuer (this module). Phase-1+:
    VaultCertificateIssuer wrapping Vault PKI engine.
    """

    async def issue(
        self,
        identity: ServiceIdentity,
        *,
        ttl: timedelta,
    ) -> IssuedCertificate:  # pragma: no cover -- Protocol body
        # Issue a leaf certificate for the identity with the given TTL.
        ...

    async def verify(
        self,
        cert: IssuedCertificate,
        *,
        now: datetime | None = None,
    ) -> None:  # pragma: no cover -- Protocol body
        # Verify the certificate is currently valid. Raises
        # CertificateExpired / CertificateRevoked / CertificateUnknown
        # on failure.
        ...

    async def revoke(
        self, cert_id: uuid.UUID
    ) -> None:  # pragma: no cover -- Protocol body
        # Mark the certificate as revoked. Subsequent verify() calls
        # raise CertificateRevoked.
        ...


class InMemoryCertificateIssuer:
    """Reference issuer: stores identity-to-cert in a dict; placeholder PEM.

    The issuer maintains a monotonic serial counter so each issued cert
    has a unique serial number. Issuance is async to match the Protocol
    contract (the Vault-backed implementation will be async).
    """

    def __init__(self, *, issuer_id: str = "verixa-mtls-inmemory") -> None:
        self._issuer_id = issuer_id
        self._issued: dict[uuid.UUID, IssuedCertificate] = {}
        self._revoked: set[uuid.UUID] = set()
        self._next_serial = 1

    @property
    def issuer_id(self) -> str:
        return self._issuer_id

    async def issue(
        self,
        identity: ServiceIdentity,
        *,
        ttl: timedelta,
    ) -> IssuedCertificate:
        if ttl <= timedelta(0):
            raise MtlsError(f"ttl must be positive; got {ttl}")
        if ttl > timedelta(days=90):
            raise MtlsError(
                f"ttl exceeds 90-day cap; got {ttl}. "
                f"Verixa policy: leaf certs MAX 90 days, typical 24 hours."
            )
        now = datetime.now(UTC)
        cert_id = uuid.uuid4()
        serial = self._next_serial
        self._next_serial += 1
        # Placeholder PEM bytes; Phase-1+ replaces with real X.509.
        pem = (
            f"-----BEGIN CERTIFICATE-----\n"
            f"VERIXA-PLACEHOLDER-CERT-ID-{cert_id}\n"
            f"SPIFFE-URI-{identity.spiffe_uri}\n"
            f"SERIAL-{serial}\n"
            f"-----END CERTIFICATE-----\n"
        ).encode()
        cert = IssuedCertificate(
            cert_id=cert_id,
            identity=identity,
            pem_bytes=pem,
            issuer_id=self._issuer_id,
            not_before=now,
            not_after=now + ttl,
            serial=serial,
        )
        self._issued[cert_id] = cert
        return cert

    async def verify(
        self,
        cert: IssuedCertificate,
        *,
        now: datetime | None = None,
    ) -> None:
        if cert.cert_id not in self._issued:
            raise CertificateUnknown(
                f"cert {cert.cert_id} was not issued by this issuer"
            )
        if cert.cert_id in self._revoked:
            raise CertificateRevoked(
                f"cert {cert.cert_id} has been revoked"
            )
        if cert.is_expired(now=now):
            raise CertificateExpired(
                f"cert {cert.cert_id} expired at {cert.not_after.isoformat()}"
            )

    async def revoke(self, cert_id: uuid.UUID) -> None:
        if cert_id not in self._issued:
            raise CertificateUnknown(
                f"cannot revoke unknown cert {cert_id}"
            )
        self._revoked.add(cert_id)


__all__ = [
    "CertificateExpired",
    "CertificateIssuer",
    "CertificateRevoked",
    "CertificateUnknown",
    "InMemoryCertificateIssuer",
    "IssuedCertificate",
    "MtlsError",
    "ServiceIdentity",
    "ServiceIdentityInvalid",
    "ServiceRole",
]
