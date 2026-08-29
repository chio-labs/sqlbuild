from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.pipeline._helpers.target_validation import (
    validate_managed_write_schemas,
    validate_project_targets,
)
from tests.unit.src.sqlbuild.compiler.pipeline._helpers.target_validation._test_types import (
    ValidateManagedWriteSchemaTestCase,
    ValidateProjectTargetsTestCase,
)
from tests.unit.src.sqlbuild.compiler.pipeline._helpers.target_validation.helpers import (
    build_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ValidateProjectTargetsTestCase(
            description="snowflake requires explicit database and schema",
            adapter_name=BuiltinAdapter.SNOWFLAKE,
            target=CompiledRelationLocation(
                database=None, schema=None, name="stg_customers", qualified_name=None
            ),
            expected_error_fragment="snowflake execution requires explicit target database, schema",
        ),
        ValidateProjectTargetsTestCase(
            description="bigquery requires explicit database and schema",
            adapter_name=BuiltinAdapter.BIGQUERY,
            target=CompiledRelationLocation(
                database=None, schema=None, name="stg_customers", qualified_name=None
            ),
            expected_error_fragment="bigquery execution requires explicit target database, schema",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_with_missing_target_namespace_when_validating_then_raises_clear_error(
    test_case: ValidateProjectTargetsTestCase,
) -> None:
    project: CompiledProject = build_project(target=test_case.target, effective_connection={})

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        validate_project_targets(adapter_name=test_case.adapter_name, project=project)


@pytest.mark.parametrize(
    "test_case",
    [
        ValidateProjectTargetsTestCase(
            description="duckdb allows missing database and schema",
            adapter_name=BuiltinAdapter.DUCKDB,
            target=CompiledRelationLocation(
                database=None,
                schema=None,
                name="stg_customers",
                qualified_name=None,
            ),
            expected_error_fragment="",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_with_missing_target_namespace_when_validating_then_it_passes(
    test_case: ValidateProjectTargetsTestCase,
) -> None:
    project: CompiledProject = build_project(target=test_case.target, effective_connection={})

    validate_project_targets(adapter_name=test_case.adapter_name, project=project)
    assert test_case.expected_error_fragment == ""


@pytest.mark.parametrize(
    "test_case",
    (
        ValidateManagedWriteSchemaTestCase(
            description="Postgres adapter default does not satisfy write policy",
            adapter=PostgresAdapter(),
            target_schema=None,
            effective_connection={},
            expected_error_fragment="Model 'stg_customers' has no explicitly resolved",
        ),
        ValidateManagedWriteSchemaTestCase(
            description="MotherDuck adapter default does not satisfy write policy",
            adapter=MotherDuckAdapter(),
            target_schema=None,
            effective_connection={},
            expected_error_fragment="Model 'stg_customers' has no explicitly resolved",
        ),
        ValidateManagedWriteSchemaTestCase(
            description="Snowflake rejects an implicit write schema",
            adapter=SnowflakeAdapter(),
            target_schema=None,
            effective_connection={},
            expected_error_fragment="Model 'stg_customers' has no explicitly resolved",
        ),
        ValidateManagedWriteSchemaTestCase(
            description="BigQuery rejects an implicit write schema",
            adapter=BigQueryAdapter(),
            target_schema=None,
            effective_connection={},
            expected_error_fragment="Model 'stg_customers' has no explicitly resolved",
        ),
        ValidateManagedWriteSchemaTestCase(
            description="Databricks rejects an implicit write schema",
            adapter=DatabricksAdapter(),
            target_schema=None,
            effective_connection={},
            expected_error_fragment="Model 'stg_customers' has no explicitly resolved",
        ),
        ValidateManagedWriteSchemaTestCase(
            description="SQL Server default does not satisfy write policy",
            adapter=SqlServerAdapter(),
            target_schema=None,
            effective_connection={},
            expected_error_fragment="Model 'stg_customers' has no explicitly resolved",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_warehouse_managed_write_without_schema_when_validating_then_error_is_raised(
    test_case: ValidateManagedWriteSchemaTestCase,
) -> None:
    project: CompiledProject = build_project(
        target=CompiledRelationLocation(
            database=None,
            schema=test_case.target_schema,
            name="stg_customers",
            qualified_name=None,
        ),
        effective_connection=test_case.effective_connection,
    )

    with pytest.raises(ValueError, match=str(test_case.expected_error_fragment)):
        validate_managed_write_schemas(adapter=test_case.adapter, project=project)


@pytest.mark.parametrize(
    "test_case",
    (
        ValidateManagedWriteSchemaTestCase(
            description="literal resolved schema satisfies write policy",
            adapter=PostgresAdapter(),
            target_schema="analytics",
            effective_connection={},
            expected_error_fragment=None,
        ),
        ValidateManagedWriteSchemaTestCase(
            description="connection schema satisfies write policy",
            adapter=PostgresAdapter(),
            target_schema=None,
            effective_connection={"schema": "analytics"},
            expected_error_fragment=None,
        ),
        ValidateManagedWriteSchemaTestCase(
            description="DuckDB permits implicit main schema",
            adapter=DuckDbAdapter(),
            target_schema=None,
            effective_connection={},
            expected_error_fragment=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_explicit_or_permitted_schema_when_validating_managed_write_then_it_passes(
    test_case: ValidateManagedWriteSchemaTestCase,
) -> None:
    project: CompiledProject = build_project(
        target=CompiledRelationLocation(
            database=None,
            schema=test_case.target_schema,
            name="stg_customers",
            qualified_name=None,
        ),
        effective_connection=test_case.effective_connection,
    )

    validate_managed_write_schemas(adapter=test_case.adapter, project=project)
    assert test_case.expected_error_fragment is None
