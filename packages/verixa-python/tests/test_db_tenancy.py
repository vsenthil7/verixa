"""pytest suite for CP-3.1 — Alembic baseline + tenancy schema.

Two layers of testing:
  1. Pure structural (always runs): alembic config valid, migration script
     imports + has right shape, MetaData includes the tenancy table.
  2. Integration (runs only when -m integration): testcontainers-Postgres
     comes up, runs `alembic upgrade head`, verifies the schema lands.

Coverage discipline: 100% on db.tenancy and db.__init__ via the structural
layer alone. Integration provides confidence that the migration *works*,
not coverage.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
MIGRATIONS_DIR = REPO_ROOT / "migrations"
MIGRATION_FILE = (
    MIGRATIONS_DIR / "versions" / "20260510_1130_baseline_tenancy.py"
)


# ---------------------------------------------------------------------------
# Alembic config
# ---------------------------------------------------------------------------


def test_alembic_ini_exists_and_parses() -> None:
    assert ALEMBIC_INI.is_file()
    cfg = Config(str(ALEMBIC_INI))
    assert cfg.get_main_option("script_location") == "migrations"


def test_alembic_can_locate_versions_dir() -> None:
    cfg = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(cfg)
    revisions = list(script.walk_revisions())
    assert len(revisions) >= 1
    revs = [r.revision for r in revisions]
    assert "20260510_1130_baseline_tenancy" in revs


def test_baseline_migration_is_genesis() -> None:
    cfg = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(cfg)
    base_revs = [
        r for r in script.walk_revisions() if r.down_revision is None
    ]
    assert len(base_revs) == 1
    assert base_revs[0].revision == "20260510_1130_baseline_tenancy"


# ---------------------------------------------------------------------------
# Migration script structural
# ---------------------------------------------------------------------------


def _load_migration_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "baseline_tenancy_migration", MIGRATION_FILE
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_module_imports_cleanly() -> None:
    module = _load_migration_module()
    assert hasattr(module, "upgrade")
    assert hasattr(module, "downgrade")
    assert hasattr(module, "revision")
    assert module.revision == "20260510_1130_baseline_tenancy"
    assert module.down_revision is None


def test_migration_upgrade_and_downgrade_are_callable() -> None:
    module = _load_migration_module()
    assert callable(module.upgrade)
    assert callable(module.downgrade)


# ---------------------------------------------------------------------------
# SQLAlchemy MetaData
# ---------------------------------------------------------------------------


def test_metadata_imports_and_has_tenancy_table() -> None:
    from verixa_runtime.db import metadata

    qualified_name = "verixa_tenancy.tenants"
    assert qualified_name in metadata.tables, (
        f"expected {qualified_name} in metadata; have {list(metadata.tables)}"
    )


def test_tenant_model_columns_match_spec() -> None:
    from verixa_runtime.db.tenancy import Tenant

    cols = {c.name: c for c in Tenant.__table__.columns}
    expected = {
        "tenant_id",
        "display_name",
        "slug",
        "deployment_tier",
        "is_active",
        "metadata_json",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(cols.keys()), (
        f"missing columns: {expected - set(cols)}"
    )


def test_tenant_table_is_in_correct_schema() -> None:
    from verixa_runtime.db.tenancy import Tenant

    assert Tenant.__table__.schema == "verixa_tenancy"


def test_tenant_slug_is_unique() -> None:
    from verixa_runtime.db.tenancy import Tenant

    slug_col = Tenant.__table__.c.slug
    assert slug_col.unique


def test_tenant_repr_includes_slug_and_id() -> None:
    from verixa_runtime.db.tenancy import Tenant

    t = Tenant()
    t.tenant_id = "00000000-0000-0000-0000-000000000001"
    t.slug = "demo"
    s = repr(t)
    assert "demo" in s
    assert "00000000-0000-0000-0000-000000000001" in s


# ---------------------------------------------------------------------------
# Naming convention sanity
# ---------------------------------------------------------------------------


def test_metadata_uses_naming_convention() -> None:
    from verixa_runtime.db import metadata

    nc = metadata.naming_convention
    for key in ("ix", "uq", "ck", "fk", "pk"):
        assert key in nc


# ---------------------------------------------------------------------------
# Integration test (requires Docker for testcontainers Postgres)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_migration_runs_against_real_postgres(tmp_path: Path) -> None:
    """Spins up a Postgres testcontainer and applies `alembic upgrade head`.

    Run with: pytest -m integration
    Requires: Docker daemon + testcontainers[postgres] installed.
    """
    pytest.importorskip("testcontainers.postgres")
    from testcontainers.postgres import PostgresContainer  # type: ignore

    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        sync_url = pg.get_connection_url()  # postgresql+psycopg2://...
        # Alembic env.py rewrites asyncpg -> psycopg; it accepts both forms
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", sync_url)

        from alembic import command

        command.upgrade(cfg, "head")

        engine = sa.create_engine(sync_url)
        with engine.connect() as conn:
            schemas = [
                r[0]
                for r in conn.execute(
                    sa.text(
                        "SELECT schema_name FROM information_schema.schemata"
                    )
                )
            ]
            assert "verixa_tenancy" in schemas
            tables = [
                r[0]
                for r in conn.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'verixa_tenancy'"
                    )
                )
            ]
            assert "tenants" in tables
