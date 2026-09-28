"""Real Snowflake coverage for executor table-type conversion."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner._helpers.planning.retention import table_type_copy_name
from sqlbuild.compiler.planner.models import TableTypePlanEntry
from sqlbuild.executor.build._helpers.retention import apply_table_type_conversion
from sqlbuild.executor.clone.main._clone_relation_operation import clone_relation_by_names
from sqlbuild.spec.contracts.types import TableType
from tests.integration.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeCloneTableTypeTestCase,
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

    apply_table_type_conversion(entry=entry, adapter=adapter, connection=connection)
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


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeCloneTableTypeTestCase(
            description="permanent origin clones as transient for a transient destination",
            origin_table_kind="TABLE",
            clone_as_transient=True,
            expected_is_transient=True,
        ),
        SnowflakeCloneTableTypeTestCase(
            description="permanent origin clones as permanent for a permanent destination",
            origin_table_kind="TABLE",
            clone_as_transient=False,
            expected_is_transient=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_permanent_snowflake_origin_when_cloning_then_clone_has_requested_type_and_rows(
    test_case: SnowflakeCloneTableTypeTestCase,
    recording_adapter: RecordingSnowflakeAdapter,
    recording_connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    adapter: RecordingSnowflakeAdapter = recording_adapter
    connection: Any = recording_connection
    origin: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="clone_type_orders_origin"
    )
    destination_name: str = "clone_type_orders_clone"
    destination: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name=destination_name
    )
    adapter.execute(
        connection=connection,
        sql=f"CREATE OR REPLACE {test_case.origin_table_kind} {origin} (id NUMBER, status VARCHAR)",
    )
    adapter.execute(
        connection=connection,
        sql=f"INSERT INTO {origin} VALUES (1, 'ready'), (2, 'complete')",
    )

    clone_relation_by_names(
        name=destination_name,
        origin_relation=origin,
        destination_relation=destination,
        origin_exists=True,
        adapter=adapter,
        connection=connection,
        hard_copy=False,
        origin_is_transient=test_case.clone_as_transient,
    )
    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection,
        database=snowflake_database,
        schemas=(snowflake_schema,),
        names=(destination_name,),
    )
    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, status FROM {destination} ORDER BY id",
    )

    assert relations[0].is_transient is test_case.expected_is_transient
    assert rows == ((1, "ready"), (2, "complete"))


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
