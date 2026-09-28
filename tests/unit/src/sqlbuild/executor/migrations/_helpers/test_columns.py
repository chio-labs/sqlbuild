"""Unit coverage for re-checking live columns before each in-place column rename."""

from __future__ import annotations

import duckdb
import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.migrations.main._read_column_events import read_column_migration_events
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent
from sqlbuild.executor.migrations._helpers.columns import apply_model_column_renames
from tests.unit.src.sqlbuild.executor.migrations._helpers._test_types import (
    OverlappingColumnRenameTestCase,
)
from tests.unit.src.sqlbuild.executor.migrations._helpers.helpers import (
    live_column_names,
    orders_connection,
    pending_rename,
    rename_then_overlap,
)


@pytest.mark.parametrize(
    "test_case",
    [
        OverlappingColumnRenameTestCase(
            description="transactional warehouse records the column another build renamed",
            transactional=True,
            expected_columns=("order_id", "revenue", "levy"),
            expected_decisions=("rename", "record"),
        ),
        OverlappingColumnRenameTestCase(
            description="non-transactional warehouse records the column another build renamed",
            transactional=False,
            expected_columns=("order_id", "revenue", "levy"),
            expected_decisions=("rename", "record"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_overlapping_build_between_renames_when_applying_then_reconciles_from_live_columns(
    test_case: OverlappingColumnRenameTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = orders_connection()
    monkeypatch.setattr(adapter, "supports_transactional_ddl", lambda: test_case.transactional)
    monkeypatch.setattr(
        adapter, "rename_column", rename_then_overlap(adapter=adapter, connection=connection)
    )

    apply_model_column_renames(
        adapter=adapter,
        connection=connection,
        entries=(
            pending_rename(origin_column="amount", destination_column="revenue"),
            pending_rename(origin_column="tax", destination_column="levy"),
        ),
        run_id="run-1",
    )
    events: tuple[ColumnMigrationEvent, ...] = read_column_migration_events(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="main",
        render_qualified_name=adapter.render_qualified_name,
    )

    assert live_column_names(connection) == test_case.expected_columns
    assert tuple(str(event.decision) for event in events) == test_case.expected_decisions


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
