from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.bigquery.helpers import bigquery_harness
from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import clickhouse_harness
from tests.e2e.src.sqlbuild.cli.commands.main.databricks.helpers import databricks_harness
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import postgres_harness
from tests.e2e.src.sqlbuild.cli.commands.main.snowflake.helpers import snowflake_harness
from tests.e2e.src.sqlbuild.cli.commands.main.sqlserver.helpers import sqlserver_harness
from tests.e2e.src.sqlbuild.cli.commands.main.warehouses.harness import (
    WarehouseHarness,
    WarehouseSetup,
)


@pytest.fixture
def warehouse(request: pytest.FixtureRequest) -> WarehouseHarness:
    """Build the harness for the warehouse an ``on_warehouses`` parameter selects."""

    setup: WarehouseSetup = request.param
    factories: dict[str, Callable[[], WarehouseHarness]] = {
        "bigquery": bigquery_harness,
        "snowflake": snowflake_harness,
        "databricks": databricks_harness,
        "postgres": lambda: postgres_harness(request.getfixturevalue("postgres_e2e_config")),
        "sqlserver": sqlserver_harness,
        "clickhouse": lambda: clickhouse_harness(request.getfixturevalue("clickhouse_e2e_config")),
    }
    return replace(factories[setup.name](), precreate_schema=setup.precreate_schema)
