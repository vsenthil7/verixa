"""Verixa SQLAlchemy MetaData root.

Every schema-namespace module imports `metadata` from here and declares
its `Table` / `DeclarativeBase` objects against it. Alembic env.py uses
this single MetaData for autogenerate.

Schema namespace map (per docs/09_data_model/DATA_MODEL.md §2):
  verixa_tenancy   — tenants, signing-key registry pointer
  verixa_registry  — agents, workflows, models, tools
  verixa_policy    — policies, policy_test_fixtures
  verixa_runtime   — active runtime state (Phase 0: minimal)
  verixa_audit     — hash-chained audit ledger + signing keys
  verixa_replay    — replay snapshot index
  verixa_review    — triad reviews, human reviews
  verixa_dossier   — compliance dossiers

Each module is imported by `verixa_runtime.db.__init__` so its tables
register against the shared MetaData before Alembic introspects.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Naming convention ensures index/constraint/fk names are stable across
# Alembic autogenerates. Critical for Auditex BLD-013 backup-before-edit
# discipline on migration files.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Shared DeclarativeBase. All ORM models inherit from this."""

    metadata = metadata


# Import schema models so they register against `metadata`. Order matters
# only for type checkers; Alembic resolves cross-schema FKs by name.
from verixa_runtime.db import audit as _audit  # noqa: E402, F401
from verixa_runtime.db import dossier as _dossier  # noqa: E402, F401
from verixa_runtime.db import policy as _policy  # noqa: E402, F401
from verixa_runtime.db import registry as _registry  # noqa: E402, F401
from verixa_runtime.db import replay as _replay  # noqa: E402, F401
from verixa_runtime.db import review as _review  # noqa: E402, F401
from verixa_runtime.db import tenancy as _tenancy  # noqa: E402, F401

__all__ = ["Base", "metadata"]
