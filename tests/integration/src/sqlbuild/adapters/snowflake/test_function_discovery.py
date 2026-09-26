"""Real Snowflake catalog discovery without an implicit connection database."""

from typing import Any

import pytest

from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from tests.integration.src.sqlbuild.adapters.snowflake.helpers import (
    build_snowflake_connection_config,
)


def test_given_no_current_database_when_discovering_udf_then_finds_explicit_target(
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    function_name = "normalize_order"
    target = ".".join(
        adapter.render_identifier(part)
        for part in (snowflake_database, snowflake_schema, function_name)
    )
    adapter.execute(
        connection=connection,
        sql=f"CREATE FUNCTION {target}(value VARCHAR) RETURNS VARCHAR LANGUAGE SQL AS 'UPPER(value)'",
    )
    config = build_snowflake_connection_config()
    config.pop("database", None)
    config.pop("schema", None)
    discovery_connection = adapter.connect(config)
    try:
        current = adapter.execute(connection=discovery_connection, sql="SELECT CURRENT_DATABASE()")
        if current.fetchone()[0] is not None:
            pytest.skip("The test user supplies a default database")
        functions = adapter.list_functions(
            connection=discovery_connection,
            database=snowflake_database,
            schemas=(snowflake_schema,),
            names=(function_name,),
        )
        assert len(functions) == 1
        assert functions[0].name == function_name
        assert functions[0].schema == snowflake_schema.lower()
        assert functions[0].database == snowflake_database
    finally:
        adapter.close(discovery_connection)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
