"""Unit coverage for per-adapter model migration staging statements."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.models import MigrationStagePlan
from sqlbuild.adapter.contract.types import MigrationTransfer
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import (
    AdapterMigrationStageTestCase,
    AdapterTransactionalDdlTestCase,
)

_STAGE: str = "dev._sqb_archive__20260102t030405z__migration_stage__stg_customer_orders"


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterMigrationStageTestCase(
            description="snowflake permanent to permanent is a zero-copy clone with grants",
            adapter=SnowflakeAdapter(),
            origin_is_transient=False,
            stage_is_transient=False,
            expected_transfer=MigrationTransfer.CLONE,
            expected_statements=(f"CREATE TABLE {_STAGE} CLONE dev.stg_orders COPY GRANTS",),
        ),
        AdapterMigrationStageTestCase(
            description="snowflake permanent to transient is a zero-copy transient clone",
            adapter=SnowflakeAdapter(),
            origin_is_transient=False,
            stage_is_transient=True,
            expected_transfer=MigrationTransfer.CLONE,
            expected_statements=(
                f"CREATE TRANSIENT TABLE {_STAGE} CLONE dev.stg_orders COPY GRANTS",
            ),
        ),
        AdapterMigrationStageTestCase(
            description="snowflake transient to transient is a zero-copy transient clone",
            adapter=SnowflakeAdapter(),
            origin_is_transient=True,
            stage_is_transient=True,
            expected_transfer=MigrationTransfer.CLONE,
            expected_statements=(
                f"CREATE TRANSIENT TABLE {_STAGE} CLONE dev.stg_orders COPY GRANTS",
            ),
        ),
        AdapterMigrationStageTestCase(
            description="snowflake transient to permanent is a physical copy into a permanent table",
            adapter=SnowflakeAdapter(),
            origin_is_transient=True,
            stage_is_transient=False,
            expected_transfer=MigrationTransfer.COPY,
            expected_statements=(
                f"CREATE TABLE {_STAGE} LIKE dev.stg_orders COPY GRANTS",
                f"INSERT INTO {_STAGE} SELECT * FROM dev.stg_orders",
            ),
        ),
        AdapterMigrationStageTestCase(
            description="snowflake without a destination type keeps the origin type",
            adapter=SnowflakeAdapter(),
            origin_is_transient=True,
            stage_is_transient=None,
            expected_transfer=MigrationTransfer.CLONE,
            expected_statements=(
                f"CREATE TRANSIENT TABLE {_STAGE} CLONE dev.stg_orders COPY GRANTS",
            ),
        ),
        AdapterMigrationStageTestCase(
            description="bigquery clones and falls back to a table copy when clone is refused",
            adapter=BigQueryAdapter(),
            origin_is_transient=False,
            stage_is_transient=None,
            expected_transfer=MigrationTransfer.CLONE,
            expected_statements=(f"CREATE TABLE `{_STAGE}` CLONE `dev.stg_orders`",),
            expected_fallback_statements=(f"CREATE TABLE `{_STAGE}` COPY `dev.stg_orders`",),
        ),
        AdapterMigrationStageTestCase(
            description="databricks copies through an independent deep clone",
            adapter=DatabricksAdapter(),
            origin_is_transient=False,
            stage_is_transient=None,
            expected_transfer=MigrationTransfer.COPY,
            expected_statements=(f"CREATE TABLE {_STAGE} DEEP CLONE dev.stg_orders",),
        ),
        AdapterMigrationStageTestCase(
            description="postgres copies into a new table without replacing anything",
            adapter=PostgresAdapter(),
            origin_is_transient=False,
            stage_is_transient=None,
            expected_transfer=MigrationTransfer.COPY,
            expected_statements=(f"CREATE TABLE {_STAGE} AS SELECT * FROM dev.stg_orders",),
        ),
        AdapterMigrationStageTestCase(
            description="sqlserver copies with select into",
            adapter=SqlServerAdapter(),
            origin_is_transient=False,
            stage_is_transient=None,
            expected_transfer=MigrationTransfer.COPY,
            expected_statements=(f"SELECT * INTO {_STAGE} FROM dev.stg_orders",),
        ),
        AdapterMigrationStageTestCase(
            description="duckdb copies into a new table without replacing anything",
            adapter=DuckDbAdapter(),
            origin_is_transient=False,
            stage_is_transient=None,
            expected_transfer=MigrationTransfer.COPY,
            expected_statements=(f"CREATE TABLE {_STAGE} AS SELECT * FROM dev.stg_orders",),
        ),
        AdapterMigrationStageTestCase(
            description="motherduck copies like duckdb",
            adapter=MotherDuckAdapter(),
            origin_is_transient=False,
            stage_is_transient=None,
            expected_transfer=MigrationTransfer.COPY,
            expected_statements=(f"CREATE TABLE {_STAGE} AS SELECT * FROM dev.stg_orders",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_when_rendering_migration_stage_then_creates_a_fresh_stage(
    test_case: AdapterMigrationStageTestCase,
) -> None:
    """Stage statements never replace or drop an existing relation."""

    plan: MigrationStagePlan = test_case.adapter.render_migration_stage(
        origin="dev.stg_orders",
        stage=_STAGE,
        origin_is_transient=test_case.origin_is_transient,
        stage_is_transient=test_case.stage_is_transient,
    )

    assert plan.transfer == test_case.expected_transfer
    assert plan.statements == test_case.expected_statements
    assert plan.fallback_statements == test_case.expected_fallback_statements


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterTransactionalDdlTestCase(
            description="snowflake ddl commits implicitly",
            adapter=SnowflakeAdapter(),
            expected_transactional=False,
        ),
        AdapterTransactionalDdlTestCase(
            description="bigquery has no transactional ddl",
            adapter=BigQueryAdapter(),
            expected_transactional=False,
        ),
        AdapterTransactionalDdlTestCase(
            description="databricks has no transactional ddl",
            adapter=DatabricksAdapter(),
            expected_transactional=False,
        ),
        AdapterTransactionalDdlTestCase(
            description="postgres renames roll back with the transaction",
            adapter=PostgresAdapter(),
            expected_transactional=True,
        ),
        AdapterTransactionalDdlTestCase(
            description="sqlserver renames roll back with the transaction",
            adapter=SqlServerAdapter(),
            expected_transactional=True,
        ),
        AdapterTransactionalDdlTestCase(
            description="duckdb renames roll back with the transaction",
            adapter=DuckDbAdapter(),
            expected_transactional=True,
        ),
        AdapterTransactionalDdlTestCase(
            description="motherduck follows duckdb transactions",
            adapter=MotherDuckAdapter(),
            expected_transactional=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_when_checking_transactional_ddl_then_reports_capability(
    test_case: AdapterTransactionalDdlTestCase,
) -> None:
    """Transactional promotion is only claimed where renames roll back."""

    assert test_case.adapter.supports_transactional_ddl() is test_case.expected_transactional


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
