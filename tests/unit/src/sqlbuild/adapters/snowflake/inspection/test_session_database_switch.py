"""A remembered session database is forgotten once a statement may switch it."""

from __future__ import annotations

import re

import pytest

from sqlbuild.adapters.snowflake.classes.snowflake_connection import _SnowflakeConnection
from tests.unit.src.sqlbuild.adapters.snowflake.inspection._test_types import (
    SessionDatabaseSwitchTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import (
    OfflineSnowflakeAdapter,
    RecordingSnowflakeWarehouse,
    build_inspection_catalog_relations,
    build_offline_snowflake,
)

_SCOPE_PATTERN: re.Pattern[str] = re.compile(r'IN SCHEMA ("[^"]+")\.')


@pytest.mark.parametrize(
    "test_case",
    [
        SessionDatabaseSwitchTestCase(
            description="USE DATABASE re-resolves build and planning lookups",
            switch_sql='USE DATABASE "ARCHIVE"',
            expected_scopes=(*('"ANALYTICS"',) * 3, *('"ARCHIVE"',) * 3),
            expected_session_reads=2,
        ),
        SessionDatabaseSwitchTestCase(
            description="commented scripting block is treated as a possible switch",
            switch_sql='-- switch\n/* block */ BEGIN\n  USE DATABASE "ARCHIVE";\nEND;',
            expected_scopes=(*('"ANALYTICS"',) * 3, *('"ARCHIVE"',) * 3),
            expected_session_reads=2,
        ),
        SessionDatabaseSwitchTestCase(
            description="statements that cannot switch databases keep the remembered one",
            switch_sql="SELECT 1",
            expected_scopes=('"ANALYTICS"',) * 6,
            expected_session_reads=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_session_switch_when_looking_up_unqualified_relations_then_uses_current_database(
    test_case: SessionDatabaseSwitchTestCase,
) -> None:
    adapter: OfflineSnowflakeAdapter
    connection: _SnowflakeConnection
    warehouse: RecordingSnowflakeWarehouse
    adapter, connection, warehouse = build_offline_snowflake(
        relations=build_inspection_catalog_relations()
    )

    _ = adapter.relation_exists(
        connection=connection, database=None, schema="staging", name="orders"
    )
    _ = adapter.read_schema_relation_listing(connection=connection, database=None, schema="staging")
    _ = adapter.execute(connection=connection, sql=test_case.switch_sql)
    _ = adapter.relation_exists(
        connection=connection, database=None, schema="staging", name="orders"
    )
    _ = adapter.read_schema_relation_listing(connection=connection, database=None, schema="staging")

    scopes: list[str] = []
    sql: str
    for sql in warehouse.attempted_sql:
        scopes.extend(match.group(1) for match in _SCOPE_PATTERN.finditer(sql))
    assert tuple(scopes) == test_case.expected_scopes
    assert len(warehouse.queries_of_kind("session")) == test_case.expected_session_reads


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
