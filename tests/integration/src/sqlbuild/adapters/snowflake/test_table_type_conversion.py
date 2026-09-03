"""Real Snowflake coverage for executor table-type conversion."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner._helpers.planning.retention import table_type_copy_name
from sqlbuild.compiler.planner.models import PlanOutput, TableTypePlanEntry
from sqlbuild.executor.build._helpers.retention import apply_table_type_conversions
from sqlbuild.spec.contracts.types import TableType
from tests.integration.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeTableTypeConversionTestCase,
)
from tests.integration.src.sqlbuild.adapters.snowflake.helpers import (
    RecordingSnowflakeAdapter,
    fetch_rows,
    qualified_name,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeTableTypeConversionTestCase(
            description="permanent table converts to transient without losing rows",
            initial_type=TableType.PERMANENT,
            initial_table_kind="TABLE",
            desired_type=TableType.TRANSIENT,
            downgrade=True,
            expected_is_transient=True,
            expected_conversion_statement_count=3,
        ),
        SnowflakeTableTypeConversionTestCase(
            description="transient table upgrades to permanent without losing rows",
            initial_type=TableType.TRANSIENT,
            initial_table_kind="TRANSIENT TABLE",
            desired_type=TableType.PERMANENT,
            downgrade=False,
            expected_is_transient=False,
            expected_conversion_statement_count=4,
        ),
        SnowflakeTableTypeConversionTestCase(
            description="permanent table already at desired type is a no-op",
            initial_type=TableType.PERMANENT,
            initial_table_kind="TABLE",
            desired_type=TableType.PERMANENT,
            downgrade=False,
            expected_is_transient=False,
            expected_conversion_statement_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_snowflake_table_when_applying_table_type_then_metadata_and_rows_are_preserved(
    test_case: SnowflakeTableTypeConversionTestCase,
    recording_adapter: RecordingSnowflakeAdapter,
    recording_connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    adapter: RecordingSnowflakeAdapter = recording_adapter
    connection: Any = recording_connection
    table_name: str = "table_type_orders"
    table_target: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name=table_name
    )
    adapter.execute(
        connection=connection,
        sql=(
            f"CREATE OR REPLACE {test_case.initial_table_kind} {table_target} "
            "(id NUMBER, status VARCHAR)"
        ),
    )
    adapter.execute(
        connection=connection,
        sql=f"INSERT INTO {table_target} VALUES (1, 'ready'), (2, 'complete')",
    )
    copy_name: str = table_type_copy_name(
        target_name=table_name, identifier_limit=adapter.maximum_identifier_length()
    )
    entry: TableTypePlanEntry = TableTypePlanEntry(
        model_name=table_name,
        destination=CompiledRelationLocation(
            database=snowflake_database,
            schema=snowflake_schema,
            name=table_name,
            qualified_name=table_target,
        ),
        copy_name=copy_name,
        desired_type=test_case.desired_type.value,
        actual_type=test_case.initial_type.value,
        source="model",
        downgrade=test_case.downgrade,
        downgrade_policy="allow",
    )
    adapter.statement_recorder.events.clear()

    apply_table_type_conversions(
        plan=PlanOutput(table_type_entries=(entry,)),
        adapter=adapter,
        connection=connection,
    )
    conversion_statement_count: int = len(adapter.statement_recorder.snapshot())
    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection,
        database=snowflake_database,
        schemas=(snowflake_schema,),
        names=(table_name, copy_name),
    )
    relation_by_name: dict[str, RelationInfo] = {relation.name: relation for relation in relations}
    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, status FROM {table_target} ORDER BY id",
    )

    assert relation_by_name[table_name].is_transient is test_case.expected_is_transient
    assert copy_name not in relation_by_name
    assert rows == ((1, "ready"), (2, "complete"))
    assert conversion_statement_count == test_case.expected_conversion_statement_count


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
