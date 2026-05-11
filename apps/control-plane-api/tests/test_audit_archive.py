"""CP-47 tests for verixa_control_plane.audit_archive -- ADR-0006 archival scaffold.

Anchored to Phase-1 carry-forward "audit ledger archival/rotation". Tests
cover the pure-function classification logic + the InMemoryLedgerArchiver
reference implementation. The Postgres-backed implementation is Phase-1+
work; this file proves the Protocol shape + classification semantics are
correct before the storage layer lands.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from verixa_control_plane.audit import AuditLedgerEntry
from verixa_control_plane.audit_archive import (
    ArchivePolicy,
    InMemoryLedgerArchiver,
    LedgerArchiver,
    RetentionTier,
    classify_tier,
    past_retention_floor,
)

_NOW = datetime(2026, 5, 11, 17, 0, 0, tzinfo=UTC)


def _entry(*, days_ago: int) -> AuditLedgerEntry:
    """Build a minimal AuditLedgerEntry whose timestamp is `days_ago` days
    before _NOW. Default fields chosen to pass the AuditLedgerEntry
    validators."""
    return AuditLedgerEntry(
        audit_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        decision="allow",
        risk_score=0.1,
        risk_classification="low",
        triad_invoked=False,
        timestamp=_NOW - timedelta(days=days_ago),
    )


# ---------------------------------------------------------------------------
# ArchivePolicy validation
# ---------------------------------------------------------------------------


def test_archive_policy_defaults_match_adr_0006() -> None:
    p = ArchivePolicy()
    assert p.hot_days == 30
    assert p.warm_days == 365
    assert p.retention_floor_days == 2555  # ~7 years


def test_archive_policy_rejects_zero_hot_days() -> None:
    with pytest.raises(ValueError, match="hot_days must be > 0"):
        ArchivePolicy(hot_days=0, warm_days=10, retention_floor_days=100)


def test_archive_policy_rejects_negative_hot_days() -> None:
    with pytest.raises(ValueError, match="hot_days must be > 0"):
        ArchivePolicy(hot_days=-1, warm_days=10, retention_floor_days=100)


def test_archive_policy_rejects_warm_le_hot() -> None:
    with pytest.raises(ValueError, match="must exceed"):
        ArchivePolicy(hot_days=30, warm_days=30, retention_floor_days=100)


def test_archive_policy_rejects_floor_le_warm() -> None:
    with pytest.raises(ValueError, match="must exceed"):
        ArchivePolicy(
            hot_days=30, warm_days=100, retention_floor_days=100
        )


# ---------------------------------------------------------------------------
# classify_tier pure-function semantics
# ---------------------------------------------------------------------------


def test_classify_tier_fresh_entry_is_hot() -> None:
    e = _entry(days_ago=0)
    assert classify_tier(e, policy=ArchivePolicy(), now=_NOW) == RetentionTier.HOT


def test_classify_tier_recent_entry_is_hot() -> None:
    e = _entry(days_ago=15)
    assert classify_tier(e, policy=ArchivePolicy(), now=_NOW) == RetentionTier.HOT


def test_classify_tier_at_hot_warm_boundary_is_warm() -> None:
    """At exactly hot_days the entry is no longer HOT -- it has crossed
    the threshold."""
    e = _entry(days_ago=30)
    assert classify_tier(e, policy=ArchivePolicy(), now=_NOW) == RetentionTier.WARM


def test_classify_tier_just_below_hot_boundary_is_hot() -> None:
    """At hot_days - 1 the entry is still HOT."""
    e = _entry(days_ago=29)
    assert classify_tier(e, policy=ArchivePolicy(), now=_NOW) == RetentionTier.HOT


def test_classify_tier_warm_entry() -> None:
    e = _entry(days_ago=100)
    assert classify_tier(e, policy=ArchivePolicy(), now=_NOW) == RetentionTier.WARM


def test_classify_tier_at_warm_cold_boundary_is_cold() -> None:
    e = _entry(days_ago=365)
    assert classify_tier(e, policy=ArchivePolicy(), now=_NOW) == RetentionTier.COLD


def test_classify_tier_just_below_cold_boundary_is_warm() -> None:
    e = _entry(days_ago=364)
    assert classify_tier(e, policy=ArchivePolicy(), now=_NOW) == RetentionTier.WARM


def test_classify_tier_old_entry_is_cold() -> None:
    e = _entry(days_ago=1000)
    assert classify_tier(e, policy=ArchivePolicy(), now=_NOW) == RetentionTier.COLD


def test_classify_tier_respects_custom_policy() -> None:
    """A custom policy with shorter windows reclassifies aggressively."""
    p = ArchivePolicy(hot_days=7, warm_days=30, retention_floor_days=365)
    e = _entry(days_ago=10)
    # In default policy this is HOT; in this aggressive policy it's WARM.
    assert classify_tier(e, policy=p, now=_NOW) == RetentionTier.WARM


# ---------------------------------------------------------------------------
# past_retention_floor
# ---------------------------------------------------------------------------


def test_past_retention_floor_fresh_entry_is_false() -> None:
    e = _entry(days_ago=10)
    assert past_retention_floor(e, policy=ArchivePolicy(), now=_NOW) is False


def test_past_retention_floor_at_boundary_is_true() -> None:
    """At exactly retention_floor_days the entry is past the floor."""
    e = _entry(days_ago=2555)
    assert past_retention_floor(e, policy=ArchivePolicy(), now=_NOW) is True


def test_past_retention_floor_well_past_floor_is_true() -> None:
    e = _entry(days_ago=3000)
    assert past_retention_floor(e, policy=ArchivePolicy(), now=_NOW) is True


def test_past_retention_floor_just_below_boundary_is_false() -> None:
    e = _entry(days_ago=2554)
    assert past_retention_floor(e, policy=ArchivePolicy(), now=_NOW) is False


# ---------------------------------------------------------------------------
# InMemoryLedgerArchiver.classify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archiver_classify_assigns_correct_tiers() -> None:
    archiver = InMemoryLedgerArchiver()
    entries = [
        _entry(days_ago=5),     # HOT
        _entry(days_ago=100),   # WARM
        _entry(days_ago=1000),  # COLD
    ]
    classified = await archiver.classify(entries, now=_NOW)
    assert len(classified) == 3
    assert classified[0].tier == RetentionTier.HOT
    assert classified[1].tier == RetentionTier.WARM
    assert classified[2].tier == RetentionTier.COLD


@pytest.mark.asyncio
async def test_archiver_classify_preserves_order() -> None:
    archiver = InMemoryLedgerArchiver()
    entries = [_entry(days_ago=d) for d in (5, 1000, 100)]
    classified = await archiver.classify(entries, now=_NOW)
    assert classified[0].age_days == 5
    assert classified[1].age_days == 1000
    assert classified[2].age_days == 100


@pytest.mark.asyncio
async def test_archiver_classify_records_age_and_classified_at() -> None:
    archiver = InMemoryLedgerArchiver()
    e = _entry(days_ago=42)
    classified = await archiver.classify([e], now=_NOW)
    assert classified[0].age_days == 42
    assert classified[0].classified_at == _NOW


@pytest.mark.asyncio
async def test_archiver_classify_empty_list() -> None:
    archiver = InMemoryLedgerArchiver()
    assert await archiver.classify([], now=_NOW) == []


@pytest.mark.asyncio
async def test_archiver_classify_defaults_now_to_utc_now() -> None:
    """Calling without now= uses datetime.now(UTC) -- smoke that no
    raise happens (we can't assert exact value without freezing time)."""
    archiver = InMemoryLedgerArchiver()
    e = _entry(days_ago=5)
    classified = await archiver.classify([e])
    # Should produce some valid classification; specific tier depends
    # on real wall-clock vs _NOW so we just check structure.
    assert classified[0].tier in {
        RetentionTier.HOT,
        RetentionTier.WARM,
        RetentionTier.COLD,
    }


# ---------------------------------------------------------------------------
# InMemoryLedgerArchiver.transitions_due
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transitions_due_detects_hot_to_warm_transition() -> None:
    """An entry classified HOT at t0 transitions to WARM by t1."""
    archiver = InMemoryLedgerArchiver()
    t0 = _NOW
    e = _entry(days_ago=29)  # HOT at _NOW
    classified_t0 = await archiver.classify([e], now=t0)
    assert classified_t0[0].tier == RetentionTier.HOT

    # Re-classify 2 days later -- entry is now 31 days old -> WARM
    t1 = t0 + timedelta(days=2)
    transitions = await archiver.transitions_due(classified_t0, now=t1)
    assert len(transitions) == 1
    assert transitions[0].tier == RetentionTier.WARM
    assert transitions[0].entry.audit_id == e.audit_id


@pytest.mark.asyncio
async def test_transitions_due_returns_empty_when_no_tier_change() -> None:
    archiver = InMemoryLedgerArchiver()
    e = _entry(days_ago=5)
    classified = await archiver.classify([e], now=_NOW)
    # Re-classify 1 day later -- still HOT
    later = _NOW + timedelta(days=1)
    transitions = await archiver.transitions_due(classified, now=later)
    assert transitions == []


@pytest.mark.asyncio
async def test_transitions_due_detects_warm_to_cold() -> None:
    archiver = InMemoryLedgerArchiver()
    e = _entry(days_ago=364)
    classified = await archiver.classify([e], now=_NOW)
    assert classified[0].tier == RetentionTier.WARM

    # 2 days later -> 366 days old -> COLD
    later = _NOW + timedelta(days=2)
    transitions = await archiver.transitions_due(classified, now=later)
    assert len(transitions) == 1
    assert transitions[0].tier == RetentionTier.COLD


@pytest.mark.asyncio
async def test_transitions_due_skips_already_correct_tier() -> None:
    """A WARM entry that's still WARM after a small time bump produces
    no transition."""
    archiver = InMemoryLedgerArchiver()
    e = _entry(days_ago=100)
    classified = await archiver.classify([e], now=_NOW)
    assert classified[0].tier == RetentionTier.WARM

    later = _NOW + timedelta(days=1)
    transitions = await archiver.transitions_due(classified, now=later)
    assert transitions == []


@pytest.mark.asyncio
async def test_transitions_due_defaults_now_to_utc_now() -> None:
    """Default-now path coverage."""
    archiver = InMemoryLedgerArchiver()
    e = _entry(days_ago=5)
    classified = await archiver.classify([e])
    transitions = await archiver.transitions_due(classified)
    # Re-classifying with same now should produce no transitions
    # (unless wall-clock moved enough to cross a boundary, which won't
    # happen in test runtime). The function returns without error.
    assert isinstance(transitions, list)


# ---------------------------------------------------------------------------
# InMemoryLedgerArchiver.beyond_retention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_beyond_retention_returns_only_floor_crossing_entries() -> None:
    archiver = InMemoryLedgerArchiver()
    entries = [
        _entry(days_ago=10),     # HOT, within floor
        _entry(days_ago=1000),   # COLD, within floor
        _entry(days_ago=3000),   # COLD, BEYOND floor
        _entry(days_ago=10000),  # COLD, BEYOND floor (way past)
    ]
    classified = await archiver.classify(entries, now=_NOW)
    beyond = await archiver.beyond_retention(classified, now=_NOW)
    assert len(beyond) == 2


@pytest.mark.asyncio
async def test_beyond_retention_empty_list() -> None:
    archiver = InMemoryLedgerArchiver()
    assert await archiver.beyond_retention([], now=_NOW) == []


@pytest.mark.asyncio
async def test_beyond_retention_no_entries_past_floor() -> None:
    archiver = InMemoryLedgerArchiver()
    entries = [_entry(days_ago=d) for d in (5, 100, 1000, 2000)]
    classified = await archiver.classify(entries, now=_NOW)
    assert await archiver.beyond_retention(classified, now=_NOW) == []


@pytest.mark.asyncio
async def test_beyond_retention_defaults_now_to_utc_now() -> None:
    """Default-now path coverage."""
    archiver = InMemoryLedgerArchiver()
    classified = await archiver.classify(
        [_entry(days_ago=5)], now=_NOW
    )
    beyond = await archiver.beyond_retention(classified)
    assert isinstance(beyond, list)


# ---------------------------------------------------------------------------
# Policy access + Protocol conformance
# ---------------------------------------------------------------------------


def test_archiver_exposes_policy() -> None:
    custom = ArchivePolicy(hot_days=7, warm_days=30, retention_floor_days=100)
    archiver = InMemoryLedgerArchiver(policy=custom)
    assert archiver.policy is custom


def test_archiver_default_policy() -> None:
    archiver = InMemoryLedgerArchiver()
    assert archiver.policy.hot_days == 30


def test_in_memory_archiver_satisfies_protocol() -> None:
    """Structural subtype check: InMemoryLedgerArchiver IS a LedgerArchiver."""
    archiver: LedgerArchiver = InMemoryLedgerArchiver()
    assert hasattr(archiver, "classify")
    assert hasattr(archiver, "transitions_due")
    assert hasattr(archiver, "beyond_retention")
