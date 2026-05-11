"""CP-47 -- Audit ledger archival + retention infrastructure (ADR-0006 scaffold).

Closes the Phase-1 carry-forward "audit ledger archival/rotation" item.
This module defines the Protocol surface; the Postgres-backed implementation
lands when the persistence-swap multi-session work happens.

Audit retention model (per ADR-0006 + Risk Register R-DATA-02 + DR Plan §4.1):

  HOT  (0..30 days)    -- in-memory or Postgres index-on-tenant_id+timestamp;
                         operator dashboards query directly; sub-second p99.
  WARM (30..365 days)  -- Postgres partition rotated monthly; queries on
                         demand; p99 < 5 seconds. Acceptable for retro audits.
  COLD (>365 days)     -- MinIO archive bucket with one parquet file per
                         month, signed + sealed via existing Replay
                         infrastructure; query requires restore + index
                         rebuild; p99 ~ minutes.

Retention floor: regulated industries typically require **7 years**
(BR-04 / NFR-12), so the cold tier is the long-term anchor. The DR
Plan §4.1 catastrophic-loss scenario assumes the cold tier survives.

Phase-0 ships:

  - ``RetentionTier``   enum (HOT / WARM / COLD)
  - ``ArchivePolicy``   frozen dataclass describing transition thresholds
  - ``ArchiveEntry``    frozen dataclass of an archived row (tier + when)
  - ``LedgerArchiver``  Protocol: classify + transition + retention-floor
  - ``InMemoryLedgerArchiver`` reference implementation: pure-function
    tier classification + transition trigger; no actual persistence

Phase-1 hardening adds:
  - PostgresLedgerArchiver wrapping partition-rotation SQL
  - MinIOColdTierWriter using existing snapshotter sealer (per ADR-0001)
  - Retention-floor enforcement (delete tier-eligible records that have
    crossed the 7-year horizon, with cryptographic-erasure audit trail
    per BR-05 + Risk Register R-DATA-03)

This module is INFRASTRUCTURE: it does not call out to storage. Callers
hand it lists of AuditLedgerEntry timestamps and it returns classifications
+ transition events. That keeps the unit-test surface pure and the
storage-specific code isolated for Phase-1 swap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol

from verixa_control_plane.audit import AuditLedgerEntry


class RetentionTier(str, Enum):
    """Storage tier an audit entry belongs to."""

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass(frozen=True, slots=True)
class ArchivePolicy:
    """Retention thresholds + retention floor.

    All durations are in days. Phase-0 defaults match ADR-0006:

      - hot_days = 30      (operator-fast tier)
      - warm_days = 365    (regulated-audit tier)
      - retention_floor_days = 2555 (~7 years, EU GDPR + UK FCA SYSC norms)

    Constraints (enforced at __post_init__):

      - 0 < hot_days < warm_days < retention_floor_days
    """

    hot_days: int = 30
    warm_days: int = 365
    retention_floor_days: int = 2555

    def __post_init__(self) -> None:
        if self.hot_days <= 0:
            raise ValueError(
                f"hot_days must be > 0; got {self.hot_days}"
            )
        if self.warm_days <= self.hot_days:
            raise ValueError(
                f"warm_days ({self.warm_days}) must exceed "
                f"hot_days ({self.hot_days})"
            )
        if self.retention_floor_days <= self.warm_days:
            raise ValueError(
                f"retention_floor_days ({self.retention_floor_days}) "
                f"must exceed warm_days ({self.warm_days})"
            )


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    """An audit entry plus its current retention tier + classification time."""

    entry: AuditLedgerEntry
    tier: RetentionTier
    classified_at: datetime
    age_days: int


def classify_tier(
    entry: AuditLedgerEntry,
    *,
    policy: ArchivePolicy,
    now: datetime,
) -> RetentionTier:
    """Pure function: which tier does this entry belong in at `now`?

    Boundary semantics: an entry exactly `hot_days` old is HOT; exactly
    `warm_days` old is WARM; anything older is COLD. (We compare with
    `<` so the day-boundary entry stays in the more-accessible tier
    until it strictly exceeds the threshold.)
    """
    age = now - entry.timestamp
    age_days = age.days
    if age_days < policy.hot_days:
        return RetentionTier.HOT
    if age_days < policy.warm_days:
        return RetentionTier.WARM
    return RetentionTier.COLD


def past_retention_floor(
    entry: AuditLedgerEntry,
    *,
    policy: ArchivePolicy,
    now: datetime,
) -> bool:
    """Return True iff this entry has crossed the retention floor.

    Past the floor, the entry is eligible for cryptographic erasure
    (BR-05 + GDPR Article 17 right-to-erasure). Implementations that
    delete must record the erasure event in a separate "tombstone
    ledger" so the audit trail itself proves the deletion happened.
    """
    age_days = (now - entry.timestamp).days
    return age_days >= policy.retention_floor_days


class LedgerArchiver(Protocol):
    """Async surface for partitioning + rotating + erasing audit ledger entries.

    Phase-0 ships InMemoryLedgerArchiver (pure classification, no I/O).
    Phase-1 ships PostgresLedgerArchiver (partition rotation SQL +
    MinIO cold-tier writes).
    """

    async def classify(
        self,
        entries: list[AuditLedgerEntry],
        *,
        now: datetime | None = None,
    ) -> list[ArchiveEntry]:  # pragma: no cover -- Protocol body
        # Classify each entry into its current tier at `now` (defaults to
        # UTC now). Returns a list of ArchiveEntry in the same order.
        ...

    async def transitions_due(
        self,
        entries: list[ArchiveEntry],
        *,
        now: datetime | None = None,
    ) -> list[ArchiveEntry]:  # pragma: no cover -- Protocol body
        # Returns the subset of entries whose tier has *just* changed and
        # whose physical storage location should be updated. Callers
        # batch these into a partition-rotation job.
        ...

    async def beyond_retention(
        self,
        entries: list[ArchiveEntry],
        *,
        now: datetime | None = None,
    ) -> list[ArchiveEntry]:  # pragma: no cover -- Protocol body
        # Returns the subset of entries that have crossed the retention
        # floor and are eligible for cryptographic erasure.
        ...


class InMemoryLedgerArchiver:
    """Pure-classification reference implementation -- no I/O.

    Holds an ArchivePolicy and uses ``classify_tier`` + ``past_retention_floor``
    to produce tier classifications. Stores no entries itself; callers
    pass entries in on each call. This keeps the unit-test surface pure
    and the storage-specific code (PostgresLedgerArchiver) isolated.
    """

    def __init__(self, policy: ArchivePolicy | None = None) -> None:
        self._policy = policy or ArchivePolicy()

    @property
    def policy(self) -> ArchivePolicy:
        return self._policy

    async def classify(
        self,
        entries: list[AuditLedgerEntry],
        *,
        now: datetime | None = None,
    ) -> list[ArchiveEntry]:
        ts_now = now or datetime.now(UTC)
        out: list[ArchiveEntry] = []
        for e in entries:
            tier = classify_tier(e, policy=self._policy, now=ts_now)
            age_days = (ts_now - e.timestamp).days
            out.append(
                ArchiveEntry(
                    entry=e,
                    tier=tier,
                    classified_at=ts_now,
                    age_days=age_days,
                )
            )
        return out

    async def transitions_due(
        self,
        entries: list[ArchiveEntry],
        *,
        now: datetime | None = None,
    ) -> list[ArchiveEntry]:
        """Return entries whose tier WOULD change if reclassified now.

        The InMemory implementation is stateless, so "would change"
        means: re-classifying now produces a different tier than the
        ArchiveEntry was previously assigned. Callers pass in entries
        from a previous classify() call; transitions_due returns the
        subset where re-running classify produces a different tier.
        """
        ts_now = now or datetime.now(UTC)
        out: list[ArchiveEntry] = []
        for ae in entries:
            new_tier = classify_tier(
                ae.entry, policy=self._policy, now=ts_now
            )
            if new_tier != ae.tier:
                age_days = (ts_now - ae.entry.timestamp).days
                out.append(
                    ArchiveEntry(
                        entry=ae.entry,
                        tier=new_tier,
                        classified_at=ts_now,
                        age_days=age_days,
                    )
                )
        return out

    async def beyond_retention(
        self,
        entries: list[ArchiveEntry],
        *,
        now: datetime | None = None,
    ) -> list[ArchiveEntry]:
        """Return the subset of entries past the retention floor.

        Callers MUST log an erasure event in a separate tombstone ledger
        before actually deleting the underlying records (BR-05 + GDPR
        Article 17 + Risk Register R-DATA-03).
        """
        ts_now = now or datetime.now(UTC)
        out: list[ArchiveEntry] = []
        for ae in entries:
            if past_retention_floor(
                ae.entry, policy=self._policy, now=ts_now
            ):
                out.append(ae)
        return out


__all__ = [
    "ArchiveEntry",
    "ArchivePolicy",
    "InMemoryLedgerArchiver",
    "LedgerArchiver",
    "RetentionTier",
    "classify_tier",
    "past_retention_floor",
]
