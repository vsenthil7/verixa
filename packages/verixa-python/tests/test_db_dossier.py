"""pytest suite for CP-3.7 — dossier schema (dossiers)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_FILE = (
    REPO_ROOT / "migrations" / "versions" / "20260510_1220_dossier_schema.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("dossier_migration", MIGRATION_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dossier_migration_chains_to_review() -> None:
    m = _load_migration()
    assert m.revision == "20260510_1220_dossier_schema"
    assert m.down_revision == "20260510_1216_review_schema"


def test_dossier_migration_callable() -> None:
    m = _load_migration()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


def test_dossier_table_in_metadata() -> None:
    from verixa_runtime.db import metadata

    assert "verixa_dossier.dossiers" in metadata.tables


def test_dossier_columns_match_spec() -> None:
    from verixa_runtime.db.dossier import Dossier

    cols = {c.name for c in Dossier.__table__.columns}
    expected = {
        "dossier_id",
        "tenant_id",
        "workflow_id",
        "time_range_start",
        "time_range_end",
        "regulator_target",
        "template_version",
        "pdf_object_key",
        "json_object_key",
        "hash_chain_proof",
        "summary",
        "generated_by",
        "generated_at",
        "expires_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_dossier_required_columns_not_null() -> None:
    """Critical columns for offline verification: PDF + JSON keys + hash proof."""
    from verixa_runtime.db.dossier import Dossier

    for required in (
        "tenant_id",
        "time_range_start",
        "time_range_end",
        "template_version",
        "pdf_object_key",
        "json_object_key",
        "hash_chain_proof",
        "summary",
        "generated_by",
    ):
        assert Dossier.__table__.c[required].nullable is False, (
            f"{required} must be NOT NULL"
        )


def test_dossier_workflow_id_is_optional() -> None:
    """Per-decision dossiers may not have a workflow scope."""
    from verixa_runtime.db.dossier import Dossier

    assert Dossier.__table__.c.workflow_id.nullable is True


def test_dossier_summary_is_jsonb() -> None:
    """summary is structured JSON for downstream rendering."""
    from verixa_runtime.db.dossier import Dossier

    summary_col = Dossier.__table__.c.summary
    # JSONB type names: 'JSONB' or contains 'jsonb'
    type_str = str(summary_col.type).lower()
    assert "json" in type_str
