"""Real Snowflake function discovery against an explicit catalog."""

from typing import Any

import pytest

from sqlbuild.adapter.contract.models import FunctionInfo
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from tests.integration.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeFunctionDiscoveryTestCase,
)
from tests.integration.src.sqlbuild.adapters.snowflake.helpers import (
    build_snowflake_connection_config,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeFunctionDiscoveryTestCase(
            description="connection without database finds the explicit target",
            function_name="normalize_order",
            expected_function_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_connection_without_database_when_discovering_udf_then_finds_explicit_target(
    test_case: SnowflakeFunctionDiscoveryTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    target: str = ".".join(
        adapter.render_identifier(part)
        for part in (snowflake_database, snowflake_schema, test_case.function_name)
    )
    adapter.execute(
        connection=connection,
        sql=f"CREATE FUNCTION {target}(value VARCHAR) RETURNS VARCHAR AS 'UPPER(value)'",
    )
    config: dict[str, object] = build_snowflake_connection_config()
    config.pop("database", None)
    config.pop("schema", None)
    discovery_connection: Any = adapter.connect(config)
    try:
        functions: tuple[FunctionInfo, ...] = adapter.list_functions(
            connection=discovery_connection,
            database=snowflake_database,
            schemas=(snowflake_schema,),
            names=(test_case.function_name,),
        )
    finally:
        adapter.close(discovery_connection)

    assert len(functions) == test_case.expected_function_count
    assert functions[0].name == test_case.function_name
    assert functions[0].schema == snowflake_schema.lower()
    assert functions[0].database == snowflake_database


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
