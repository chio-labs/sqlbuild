"""Unit coverage for decoding hand-written persisted migration state rows."""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from sqlbuild._native import read_migration_state_events, stored_old_name_view_columns
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent, OldNameViewEvent
from sqlbuild.compiler.migrations.types import OldNameViewDropReason
from tests.unit.src.sqlbuild.compiler.migrations.main._test_types import (
    StoredColumnRowTestCase,
    StoredOldNameRowTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StoredOldNameRowTestCase(
            description="stored aliases are sorted and grants keep their order",
            column_aliases_sql="""'{"b":"total","a":"amount"}'""",
            grants_copied_sql="""'["GRANT SELECT ON main.orders TO reporting"]'""",
            drop_reason_sql="'early'",
            expected_aliases=(("a", "amount"), ("b", "total")),
            expected_grants=("GRANT SELECT ON main.orders TO reporting",),
            expected_drop_reason=OldNameViewDropReason.EARLY,
        ),
        StoredOldNameRowTestCase(
            description="unreadable JSON and an unknown drop reason read as absent",
            column_aliases_sql="'{not json'",
            grants_copied_sql="""'{"a": 1}'""",
            drop_reason_sql="'from_a_future_version'",
            expected_aliases=(),
            expected_grants=None,
            expected_drop_reason=None,
        ),
        StoredOldNameRowTestCase(
            description="null columns read as no aliases and unknown grants",
            column_aliases_sql="NULL",
            grants_copied_sql="NULL",
            drop_reason_sql="NULL",
            expected_aliases=(),
            expected_grants=None,
            expected_drop_reason=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_persisted_old_name_row_when_reading_then_codecs_decode_stored_text(
    test_case: StoredOldNameRowTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    _ = connection.execute(
        adapter.render_create_old_name_view_state_table_sql(database=None, schema="main")
    )
    _ = connection.execute(
        "INSERT INTO main._sqlbuild_old_name_views (event_id, event_type, migration_event_id, "
        "destination_model, old_schema, old_name, new_schema, new_name, column_aliases, "
        "grants_copied, drop_reason, run_id, created_at) VALUES ('fact', 'view_dropped', 'move', "
        "'daily_orders', 'main', 'orders', 'main', 'daily_orders', "
        f"{test_case.column_aliases_sql}, {test_case.grants_copied_sql}, "
        f"{test_case.drop_reason_sql}, 'run-1', '2026-01-02T03:04:05+00:00')"
    )

    stored: tuple[OldNameViewEvent, ...] = read_migration_state_events(
        kind="old_name",
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="main",
        stored_columns=stored_old_name_view_columns(
            adapter=adapter, connection=connection, database=None, schema="main"
        ),
        render_qualified_name=adapter.render_qualified_name,
    )

    assert len(stored) == 1
    assert stored[0].column_aliases == test_case.expected_aliases
    assert stored[0].grants_copied == test_case.expected_grants
    assert stored[0].drop_reason == test_case.expected_drop_reason
    assert stored[0].created_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    [
        StoredColumnRowTestCase(
            description="rows with a decision from a newer version are skipped",
            decisions=("rename", "decided_by_a_future_version", "record"),
            expected_decisions=("rename", "record"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_persisted_column_rows_when_reading_then_unknown_rows_are_skipped_in_order(
    test_case: StoredColumnRowTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    _ = connection.execute(
        adapter.render_create_column_migration_state_table_sql(database=None, schema="main")
    )
    index: int
    decision: str
    for index, decision in enumerate(test_case.decisions):
        _ = connection.execute(
            "INSERT INTO main._sqlbuild_column_migrations (event_id, model_name, relation_schema, "
            "relation_name, origin_column, destination_column, discovery, decision, run_id, "
            f"created_at) VALUES ('event-{index}', 'orders', 'main', 'orders', 'amount', "
            f"'total', 'manual', '{decision}', 'run-{index}', '2026-01-0{index + 1}')"
        )

    stored: tuple[ColumnMigrationEvent, ...] = read_migration_state_events(
        kind="column",
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="main",
        render_qualified_name=adapter.render_qualified_name,
    )

    assert tuple(event.decision.value for event in stored) == test_case.expected_decisions


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
