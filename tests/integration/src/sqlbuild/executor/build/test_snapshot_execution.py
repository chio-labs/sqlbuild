"""Integration tests for snapshot build execution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.build._test_types import (
    BuildExecutionTestCase,
    SnapshotCheckExecutionTestCase,
    SnapshotCheckFailureTestCase,
    SnapshotHardDeleteExecutionTestCase,
    SnapshotHistoricalCheckExecutionTestCase,
    SnapshotHistoricalTimestampExecutionTestCase,
    SnapshotTimestampExecutionTestCase,
    SnapshotTimestampFailureTestCase,
)
from tests.integration.src.sqlbuild.executor.build.helpers import (
    run_build_for_project,
    verify_model_statuses,
)

_PROJECT_YML: str = (
    'name = "demo"\n'
    'adapter = "duckdb"\n\n'
    "[connection]\n"
    'database = ":memory:"\n\n'
    "[settings]\n"
    'default_audit_severity = "error"\n'
)

_NOT_NULL_AUDIT: str = 'AUDIT ();\n\nSELECT @column FROM __ref("@model") WHERE @column IS NULL'


SNAPSHOT_TIMESTAMP_TEST_CASES: list[SnapshotTimestampExecutionTestCase] = [
    SnapshotTimestampExecutionTestCase(
        description="current-state timestamp snapshot tracks changed rows",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        stale_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2023-12-31 00:00:00' AS updated_at",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at "
            "UNION ALL SELECT 2 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_stale_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "pro", "2024-01-03 00:00:00", None),
            (2, "basic", "2024-01-02 00:00:00", None),
        ),
    ),
    SnapshotTimestampExecutionTestCase(
        description="current-state timestamp snapshot supports composite unique keys",
        model_name="customer_region_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_regions\n"
                "    schema: main\n"
                "    table: raw_customer_regions\n"
            ),
            "models/customer_region_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id, region],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                "SELECT customer_id, region, plan, updated_at "
                'FROM __source("raw_customer_regions")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        stale_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'stale' AS plan, "
            "TIMESTAMP '2023-12-31 00:00:00' AS updated_at "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, region, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_region_snapshot "
            "ORDER BY customer_id, region DESC, valid_from"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=(
            (1, "us", "basic", "2024-01-01 00:00:00", None),
            (1, "eu", "basic", "2024-01-01 00:00:00", None),
        ),
        expected_stale_rows=(
            (1, "us", "basic", "2024-01-01 00:00:00", None),
            (1, "eu", "basic", "2024-01-01 00:00:00", None),
        ),
        expected_changed_rows=(
            (1, "us", "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "us", "pro", "2024-01-03 00:00:00", None),
            (1, "eu", "basic", "2024-01-01 00:00:00", None),
        ),
    ),
    SnapshotTimestampExecutionTestCase(
        description="current-state timestamp snapshot supports custom validity columns",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  valid_from_column effective_from,\n"
                "  valid_to_column effective_to\n"
                ");\n\n"
                'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        stale_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2023-12-31 00:00:00' AS updated_at",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, plan, CAST(effective_from AS VARCHAR), "
            "CAST(effective_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, effective_from"
        ),
        expected_validity_columns=("effective_from", "effective_to"),
        expected_initial_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_stale_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "pro", "2024-01-03 00:00:00", None),
        ),
    ),
]

SNAPSHOT_TIMESTAMP_FAILURE_TEST_CASES: list[SnapshotTimestampFailureTestCase] = [
    SnapshotTimestampFailureTestCase(
        description="duplicate source unique key fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
            "UNION ALL SELECT 1 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        ),
        expected_error_fragment=(
            "source query returned multiple rows for the same unique_key (customer_id)"
        ),
    ),
    SnapshotTimestampFailureTestCase(
        description="validity column collision fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                "SELECT customer_id, updated_at, updated_at AS valid_from "
                'FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_error_fragment="query output includes generated validity columns: valid_from",
    ),
    SnapshotTimestampFailureTestCase(
        description="custom validity column collision fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  valid_from_column effective_from,\n"
                "  valid_to_column effective_to\n"
                ");\n\n"
                "SELECT customer_id, updated_at, updated_at AS effective_from "
                'FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_error_fragment="query output includes generated validity columns: effective_from",
    ),
    SnapshotTimestampFailureTestCase(
        description="custom validity column collision is case-insensitive",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  valid_from_column effective_from,\n"
                "  valid_to_column effective_to\n"
                ");\n\n"
                "SELECT customer_id, updated_at, updated_at AS EFFECTIVE_FROM "
                'FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_error_fragment="query output includes generated validity columns: effective_from",
    ),
    SnapshotTimestampFailureTestCase(
        description="historical timestamp snapshot duplicate identity fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_extracts\n"
                "    schema: main\n"
                "    table: raw_customer_extracts\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  observed_at observed_at,\n"
                "  historical_input snapshot\n"
                ");\n\n"
                "SELECT customer_id, plan, updated_at, observed_at "
                'FROM __source("raw_customer_extracts")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customer_extracts AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-02' AS observed_at "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-03', "
            "TIMESTAMP '2024-01-02'",
        ),
        expected_error_fragment=(
            "source query returned multiple rows for the same snapshot identity "
            "(customer_id, observed_at)"
        ),
    ),
    SnapshotTimestampFailureTestCase(
        description="historical timestamp changes duplicate identity fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_changes\n"
                "    schema: main\n"
                "    table: raw_customer_changes\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  observed_at observed_at,\n"
                "  historical_input changes\n"
                ");\n\n"
                "SELECT customer_id, plan, updated_at, observed_at "
                'FROM __source("raw_customer_changes")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customer_changes AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-02' AS observed_at "
            "UNION ALL SELECT 1, 'basic-duplicate', TIMESTAMP '2024-01-01', "
            "TIMESTAMP '2024-01-03'",
        ),
        expected_error_fragment=(
            "source query returned multiple rows for the same snapshot identity "
            "(customer_id, updated_at)"
        ),
    ),
]

SNAPSHOT_HISTORICAL_TIMESTAMP_TEST_CASES: list[SnapshotHistoricalTimestampExecutionTestCase] = [
    SnapshotHistoricalTimestampExecutionTestCase(
        description="historical timestamp snapshot uses updated_at validity",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_extracts\n"
                "    schema: main\n"
                "    table: raw_customer_extracts\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  observed_at observed_at,\n"
                "  historical_input snapshot\n"
                ");\n\n"
                "SELECT customer_id, plan, updated_at, observed_at "
                'FROM __source("raw_customer_extracts")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_extracts AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-02' AS observed_at "
            "UNION ALL SELECT 1, 'basic', TIMESTAMP '2024-01-01', "
            "TIMESTAMP '2024-01-03' "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-04', "
            "TIMESTAMP '2024-01-06'",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_extracts AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-02' AS observed_at "
            "UNION ALL SELECT 1, 'basic', TIMESTAMP '2024-01-01', "
            "TIMESTAMP '2024-01-03' "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-04', "
            "TIMESTAMP '2024-01-06' "
            "UNION ALL SELECT 1, 'team', TIMESTAMP '2024-01-07', "
            "TIMESTAMP '2024-01-08' "
            "UNION ALL SELECT 2, 'basic', TIMESTAMP '2024-01-05', "
            "TIMESTAMP '2024-01-06'",
        ),
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (1, "pro", "2024-01-04 00:00:00", None),
        ),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (1, "pro", "2024-01-04 00:00:00", "2024-01-07 00:00:00"),
            (1, "team", "2024-01-07 00:00:00", None),
            (2, "basic", "2024-01-05 00:00:00", None),
        ),
    ),
    SnapshotHistoricalTimestampExecutionTestCase(
        description="historical timestamp snapshot supports composite unique keys",
        model_name="customer_region_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_region_extracts\n"
                "    schema: main\n"
                "    table: raw_customer_region_extracts\n"
            ),
            "models/customer_region_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id, region],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  observed_at observed_at,\n"
                "  historical_input snapshot\n"
                ");\n\n"
                "SELECT customer_id, region, plan, updated_at, observed_at "
                'FROM __source("raw_customer_region_extracts")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_region_extracts AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, TIMESTAMP '2024-01-02' AS observed_at "
            "UNION ALL SELECT 1, 'eu', 'basic', TIMESTAMP '2024-01-01', "
            "TIMESTAMP '2024-01-02' "
            "UNION ALL SELECT 1, 'eu', 'pro', TIMESTAMP '2024-01-03', "
            "TIMESTAMP '2024-01-04'",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_region_extracts AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, TIMESTAMP '2024-01-02' AS observed_at "
            "UNION ALL SELECT 1, 'us', 'team', TIMESTAMP '2024-01-05', "
            "TIMESTAMP '2024-01-06' "
            "UNION ALL SELECT 1, 'eu', 'basic', TIMESTAMP '2024-01-01', "
            "TIMESTAMP '2024-01-02' "
            "UNION ALL SELECT 1, 'eu', 'pro', TIMESTAMP '2024-01-03', "
            "TIMESTAMP '2024-01-04'",
        ),
        expected_query=(
            "SELECT customer_id, region, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_region_snapshot "
            "ORDER BY customer_id, region, valid_from"
        ),
        expected_initial_rows=(
            (1, "eu", "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "eu", "pro", "2024-01-03 00:00:00", None),
            (1, "us", "basic", "2024-01-01 00:00:00", None),
        ),
        expected_changed_rows=(
            (1, "eu", "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "eu", "pro", "2024-01-03 00:00:00", None),
            (1, "us", "basic", "2024-01-01 00:00:00", "2024-01-05 00:00:00"),
            (1, "us", "team", "2024-01-05 00:00:00", None),
        ),
    ),
    SnapshotHistoricalTimestampExecutionTestCase(
        description="historical timestamp snapshot ignores observed_at initial validity",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_extracts\n"
                "    schema: main\n"
                "    table: raw_customer_extracts\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  observed_at observed_at,\n"
                "  historical_input snapshot,\n"
                "  initial_valid_from observed_at\n"
                ");\n\n"
                "SELECT customer_id, plan, updated_at, observed_at "
                'FROM __source("raw_customer_extracts")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_extracts AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-05' AS observed_at",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_extracts AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-05' AS observed_at "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-03', "
            "TIMESTAMP '2024-01-06'",
        ),
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "pro", "2024-01-03 00:00:00", None),
        ),
    ),
    SnapshotHistoricalTimestampExecutionTestCase(
        description="historical timestamp changes allow multiple changes in one batch",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_changes\n"
                "    schema: main\n"
                "    table: raw_customer_changes\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  observed_at observed_at,\n"
                "  historical_input changes\n"
                ");\n\n"
                "SELECT customer_id, plan, updated_at, observed_at "
                'FROM __source("raw_customer_changes")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_changes AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-10' AS observed_at "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-04', "
            "TIMESTAMP '2024-01-10' "
            "UNION ALL SELECT 1, 'team', TIMESTAMP '2024-01-07', "
            "TIMESTAMP '2024-01-10'",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_changes AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-10' AS observed_at "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-04', "
            "TIMESTAMP '2024-01-10' "
            "UNION ALL SELECT 1, 'team', TIMESTAMP '2024-01-07', "
            "TIMESTAMP '2024-01-10' "
            "UNION ALL SELECT 1, 'enterprise', TIMESTAMP '2024-01-12', "
            "TIMESTAMP '2024-01-13' "
            "UNION ALL SELECT 2, 'basic', TIMESTAMP '2024-01-05', "
            "TIMESTAMP '2024-01-13'",
        ),
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (1, "pro", "2024-01-04 00:00:00", "2024-01-07 00:00:00"),
            (1, "team", "2024-01-07 00:00:00", None),
        ),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (1, "pro", "2024-01-04 00:00:00", "2024-01-07 00:00:00"),
            (1, "team", "2024-01-07 00:00:00", "2024-01-12 00:00:00"),
            (1, "enterprise", "2024-01-12 00:00:00", None),
            (2, "basic", "2024-01-05 00:00:00", None),
        ),
    ),
    SnapshotHistoricalTimestampExecutionTestCase(
        description=(
            "historical timestamp changes support composite keys and ignore initial observed_at"
        ),
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_region_changes\n"
                "    schema: main\n"
                "    table: raw_customer_region_changes\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id, region],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  observed_at observed_at,\n"
                "  historical_input changes,\n"
                "  initial_valid_from observed_at\n"
                ");\n\n"
                "SELECT customer_id, region, plan, updated_at, observed_at "
                'FROM __source("raw_customer_region_changes")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_region_changes AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-10' AS observed_at "
            "UNION ALL SELECT 1, 'eu', 'basic', TIMESTAMP '2024-01-02', "
            "TIMESTAMP '2024-01-10' "
            "UNION ALL SELECT 1, 'us', 'pro', TIMESTAMP '2024-01-04', "
            "TIMESTAMP '2024-01-10'",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_region_changes AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-10' AS observed_at "
            "UNION ALL SELECT 1, 'eu', 'basic', TIMESTAMP '2024-01-02', "
            "TIMESTAMP '2024-01-10' "
            "UNION ALL SELECT 1, 'us', 'pro', TIMESTAMP '2024-01-04', "
            "TIMESTAMP '2024-01-10' "
            "UNION ALL SELECT 1, 'eu', 'team', TIMESTAMP '2024-01-05', "
            "TIMESTAMP '2024-01-11'",
        ),
        expected_query=(
            "SELECT customer_id, region, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, region, valid_from"
        ),
        expected_initial_rows=(
            (1, "eu", "basic", "2024-01-02 00:00:00", None),
            (1, "us", "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (1, "us", "pro", "2024-01-04 00:00:00", None),
        ),
        expected_changed_rows=(
            (1, "eu", "basic", "2024-01-02 00:00:00", "2024-01-05 00:00:00"),
            (1, "eu", "team", "2024-01-05 00:00:00", None),
            (1, "us", "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (1, "us", "pro", "2024-01-04 00:00:00", None),
        ),
    ),
    SnapshotHistoricalTimestampExecutionTestCase(
        description="historical timestamp snapshot invalidates missing keys at observed_at",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_extracts\n"
                "    schema: main\n"
                "    table: raw_customer_extracts\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  observed_at observed_at,\n"
                "  historical_input snapshot,\n"
                "  invalidate_hard_deletes true\n"
                ");\n\n"
                "SELECT customer_id, plan, updated_at, observed_at "
                'FROM __source("raw_customer_extracts")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_extracts AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-02' AS observed_at "
            "UNION ALL SELECT 2, 'basic', TIMESTAMP '2024-01-01', "
            "TIMESTAMP '2024-01-02' "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-03', "
            "TIMESTAMP '2024-01-04'",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_extracts AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS updated_at, "
            "TIMESTAMP '2024-01-02' AS observed_at "
            "UNION ALL SELECT 2, 'basic', TIMESTAMP '2024-01-01', "
            "TIMESTAMP '2024-01-02' "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-03', "
            "TIMESTAMP '2024-01-04' "
            "UNION ALL SELECT 2, 'team', TIMESTAMP '2024-01-06', "
            "TIMESTAMP '2024-01-07'",
        ),
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "pro", "2024-01-03 00:00:00", None),
            (2, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
        ),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "pro", "2024-01-03 00:00:00", "2024-01-07 00:00:00"),
            (2, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (2, "team", "2024-01-06 00:00:00", None),
        ),
    ),
]

SNAPSHOT_CHECK_TEST_CASES: list[SnapshotCheckExecutionTestCase] = [
    SnapshotCheckExecutionTestCase(
        description="current-state check snapshot tracks checked column changes only",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status]\n"
                ");\n\n"
                'SELECT customer_id, plan, status FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status",
        ),
        unchecked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, 'active' AS status",
        ),
        checked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, 'paused' AS status "
            "UNION ALL SELECT 2 AS customer_id, 'basic' AS plan, 'active' AS status",
        ),
        expected_query=(
            "SELECT customer_id, plan, status, valid_to IS NULL "
            "FROM main.customer_snapshot ORDER BY customer_id, valid_to IS NULL, plan"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=((1, "basic", "active", True),),
        expected_unchecked_rows=((1, "basic", "active", True),),
        expected_checked_rows=(
            (1, "basic", "active", False),
            (1, "pro", "paused", True),
            (2, "basic", "active", True),
        ),
    ),
    SnapshotCheckExecutionTestCase(
        description="current-state check snapshot supports composite unique keys",
        model_name="customer_region_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_regions\n"
                "    schema: main\n"
                "    table: raw_customer_regions\n"
            ),
            "models/customer_region_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id, region],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status]\n"
                ");\n\n"
                "SELECT customer_id, region, plan, status "
                'FROM __source("raw_customer_regions")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, 'active' AS status "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "'active' AS status",
        ),
        unchecked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'pro' AS plan, 'active' AS status "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "'active' AS status",
        ),
        checked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'pro' AS plan, 'paused' AS status "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "'active' AS status",
        ),
        expected_query=(
            "SELECT customer_id, region, plan, status, valid_to IS NULL "
            "FROM main.customer_region_snapshot "
            "ORDER BY customer_id, region DESC, valid_to IS NULL, plan"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=(
            (1, "us", "basic", "active", True),
            (1, "eu", "basic", "active", True),
        ),
        expected_unchecked_rows=(
            (1, "us", "basic", "active", True),
            (1, "eu", "basic", "active", True),
        ),
        expected_checked_rows=(
            (1, "us", "basic", "active", False),
            (1, "us", "pro", "paused", True),
            (1, "eu", "basic", "active", True),
        ),
    ),
    SnapshotCheckExecutionTestCase(
        description="current-state check snapshot compares null values safely",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status]\n"
                ");\n\n"
                'SELECT customer_id, plan, status FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, NULL::VARCHAR AS status",
        ),
        unchecked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, NULL::VARCHAR AS status",
        ),
        checked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, 'active' AS status",
        ),
        expected_query=(
            "SELECT customer_id, plan, status, valid_to IS NULL "
            "FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_to IS NULL, status NULLS FIRST"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=((1, "basic", None, True),),
        expected_unchecked_rows=((1, "basic", None, True),),
        expected_checked_rows=(
            (1, "basic", None, False),
            (1, "pro", "active", True),
        ),
    ),
    SnapshotCheckExecutionTestCase(
        description="current-state check snapshot tracks value to null changes",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status]\n"
                ");\n\n"
                'SELECT customer_id, plan, status FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status",
        ),
        unchecked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, 'active' AS status",
        ),
        checked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, NULL::VARCHAR AS status",
        ),
        expected_query=(
            "SELECT customer_id, plan, status, valid_to IS NULL "
            "FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_to IS NULL, status NULLS FIRST"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=((1, "basic", "active", True),),
        expected_unchecked_rows=((1, "basic", "active", True),),
        expected_checked_rows=(
            (1, "basic", "active", False),
            (1, "pro", None, True),
        ),
    ),
    SnapshotCheckExecutionTestCase(
        description="current-state check snapshot supports multiple check columns",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status, tier]\n"
                ");\n\n"
                'SELECT customer_id, plan, status, tier FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status, 'bronze' AS tier",
        ),
        unchecked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, 'active' AS status, 'bronze' AS tier",
        ),
        checked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, 'active' AS status, 'gold' AS tier",
        ),
        expected_query=(
            "SELECT customer_id, plan, status, tier, valid_to IS NULL "
            "FROM main.customer_snapshot ORDER BY customer_id, valid_to IS NULL, tier"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=((1, "basic", "active", "bronze", True),),
        expected_unchecked_rows=((1, "basic", "active", "bronze", True),),
        expected_checked_rows=(
            (1, "basic", "active", "bronze", False),
            (1, "pro", "active", "gold", True),
        ),
    ),
    SnapshotCheckExecutionTestCase(
        description="current-state check snapshot supports composite keys with multiple checks",
        model_name="customer_region_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_regions\n"
                "    schema: main\n"
                "    table: raw_customer_regions\n"
            ),
            "models/customer_region_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id, region],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status, tier]\n"
                ");\n\n"
                "SELECT customer_id, region, plan, status, tier "
                'FROM __source("raw_customer_regions")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "'active' AS status, 'bronze' AS tier "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "'active' AS status, 'bronze' AS tier",
        ),
        unchecked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'pro' AS plan, "
            "'active' AS status, 'bronze' AS tier "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "'active' AS status, 'bronze' AS tier",
        ),
        checked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'pro' AS plan, "
            "'active' AS status, 'gold' AS tier "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "'active' AS status, 'bronze' AS tier "
            "UNION ALL SELECT 2 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "'active' AS status, 'bronze' AS tier",
        ),
        expected_query=(
            "SELECT customer_id, region, plan, status, tier, valid_to IS NULL "
            "FROM main.customer_region_snapshot "
            "ORDER BY customer_id, region DESC, valid_to IS NULL, tier"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=(
            (1, "us", "basic", "active", "bronze", True),
            (1, "eu", "basic", "active", "bronze", True),
        ),
        expected_unchecked_rows=(
            (1, "us", "basic", "active", "bronze", True),
            (1, "eu", "basic", "active", "bronze", True),
        ),
        expected_checked_rows=(
            (1, "us", "basic", "active", "bronze", False),
            (1, "us", "pro", "active", "gold", True),
            (1, "eu", "basic", "active", "bronze", True),
            (2, "us", "basic", "active", "bronze", True),
        ),
    ),
    SnapshotCheckExecutionTestCase(
        description="current-state check snapshot supports custom validity columns",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status],\n"
                "  valid_from_column effective_from,\n"
                "  valid_to_column effective_to\n"
                ");\n\n"
                'SELECT customer_id, plan, status FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status",
        ),
        unchecked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, 'active' AS status",
        ),
        checked_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, 'paused' AS status",
        ),
        expected_query=(
            "SELECT customer_id, plan, status, effective_to IS NULL "
            "FROM main.customer_snapshot ORDER BY customer_id, effective_to IS NULL, plan"
        ),
        expected_validity_columns=("effective_from", "effective_to"),
        expected_initial_rows=((1, "basic", "active", True),),
        expected_unchecked_rows=((1, "basic", "active", True),),
        expected_checked_rows=(
            (1, "basic", "active", False),
            (1, "pro", "paused", True),
        ),
    ),
]

SNAPSHOT_HISTORICAL_CHECK_TEST_CASES: list[SnapshotHistoricalCheckExecutionTestCase] = [
    SnapshotHistoricalCheckExecutionTestCase(
        description="historical check snapshot builds collapsed history from observations",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_daily\n"
                "    schema: main\n"
                "    table: raw_customer_daily\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [plan],\n"
                "  observed_at observed_at\n"
                ");\n\n"
                'SELECT customer_id, plan, observed_at FROM __source("raw_customer_daily")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_daily AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-02' "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-03' "
            "UNION ALL SELECT 1, 'team', TIMESTAMP '2024-01-04'",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_daily AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-02' "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-03' "
            "UNION ALL SELECT 1, 'team', TIMESTAMP '2024-01-04' "
            "UNION ALL SELECT 1, 'enterprise', TIMESTAMP '2024-01-05' "
            "UNION ALL SELECT 2, 'basic', TIMESTAMP '2024-01-03'",
        ),
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
            (1, "pro", "2024-01-02 00:00:00", "2024-01-04 00:00:00"),
            (1, "team", "2024-01-04 00:00:00", None),
        ),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
            (1, "pro", "2024-01-02 00:00:00", "2024-01-04 00:00:00"),
            (1, "team", "2024-01-04 00:00:00", "2024-01-05 00:00:00"),
            (1, "enterprise", "2024-01-05 00:00:00", None),
            (2, "basic", "2024-01-03 00:00:00", None),
        ),
    ),
    SnapshotHistoricalCheckExecutionTestCase(
        description="historical check snapshot supports composite unique keys",
        model_name="customer_region_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_region_daily\n"
                "    schema: main\n"
                "    table: raw_customer_region_daily\n"
            ),
            "models/customer_region_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id, region],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [plan],\n"
                "  observed_at observed_at\n"
                ");\n\n"
                "SELECT customer_id, region, plan, observed_at "
                'FROM __source("raw_customer_region_daily")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_region_daily AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at "
            "UNION ALL SELECT 1, 'us', 'basic', TIMESTAMP '2024-01-02' "
            "UNION ALL SELECT 1, 'eu', 'basic', TIMESTAMP '2024-01-01' "
            "UNION ALL SELECT 1, 'eu', 'pro', TIMESTAMP '2024-01-03'",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_region_daily AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at "
            "UNION ALL SELECT 1, 'us', 'basic', TIMESTAMP '2024-01-02' "
            "UNION ALL SELECT 1, 'us', 'team', TIMESTAMP '2024-01-04' "
            "UNION ALL SELECT 1, 'eu', 'basic', TIMESTAMP '2024-01-01' "
            "UNION ALL SELECT 1, 'eu', 'pro', TIMESTAMP '2024-01-03' "
            "UNION ALL SELECT 2, 'us', 'basic', TIMESTAMP '2024-01-02'",
        ),
        expected_query=(
            "SELECT customer_id, region, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_region_snapshot "
            "ORDER BY customer_id, region, valid_from"
        ),
        expected_initial_rows=(
            (1, "eu", "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "eu", "pro", "2024-01-03 00:00:00", None),
            (1, "us", "basic", "2024-01-01 00:00:00", None),
        ),
        expected_changed_rows=(
            (1, "eu", "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "eu", "pro", "2024-01-03 00:00:00", None),
            (1, "us", "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (1, "us", "team", "2024-01-04 00:00:00", None),
            (2, "us", "basic", "2024-01-02 00:00:00", None),
        ),
    ),
    SnapshotHistoricalCheckExecutionTestCase(
        description="historical check snapshot accepts initial_valid_from observed_at",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_daily\n"
                "    schema: main\n"
                "    table: raw_customer_daily\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [plan],\n"
                "  observed_at observed_at,\n"
                "  initial_valid_from observed_at\n"
                ");\n\n"
                'SELECT customer_id, plan, observed_at FROM __source("raw_customer_daily")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_daily AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_daily AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at "
            "UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-03'",
        ),
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "pro", "2024-01-03 00:00:00", None),
        ),
    ),
    SnapshotHistoricalCheckExecutionTestCase(
        description="historical check snapshot invalidates missing composite keys",
        model_name="customer_region_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_region_daily\n"
                "    schema: main\n"
                "    table: raw_customer_region_daily\n"
            ),
            "models/customer_region_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id, region],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [plan],\n"
                "  observed_at observed_at,\n"
                "  invalidate_hard_deletes true\n"
                ");\n\n"
                "SELECT customer_id, region, plan, observed_at "
                'FROM __source("raw_customer_region_daily")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_region_daily AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at "
            "UNION ALL SELECT 1, 'eu', 'basic', TIMESTAMP '2024-01-01' "
            "UNION ALL SELECT 1, 'us', 'pro', TIMESTAMP '2024-01-02'",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_region_daily AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at "
            "UNION ALL SELECT 1, 'eu', 'basic', TIMESTAMP '2024-01-01' "
            "UNION ALL SELECT 1, 'us', 'pro', TIMESTAMP '2024-01-02' "
            "UNION ALL SELECT 1, 'eu', 'team', TIMESTAMP '2024-01-03'",
        ),
        expected_query=(
            "SELECT customer_id, region, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_region_snapshot "
            "ORDER BY customer_id, region, valid_from"
        ),
        expected_initial_rows=(
            (1, "eu", "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
            (1, "us", "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
            (1, "us", "pro", "2024-01-02 00:00:00", None),
        ),
        expected_changed_rows=(
            (1, "eu", "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
            (1, "eu", "team", "2024-01-03 00:00:00", None),
            (1, "us", "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
            (1, "us", "pro", "2024-01-02 00:00:00", "2024-01-03 00:00:00"),
        ),
    ),
]

SNAPSHOT_CHECK_FAILURE_TEST_CASES: list[SnapshotCheckFailureTestCase] = [
    SnapshotCheckFailureTestCase(
        description="check snapshot duplicate source unique key fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status]\n"
                ");\n\n"
                'SELECT customer_id, status FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'active' AS status "
            "UNION ALL SELECT 1 AS customer_id, 'paused' AS status",
        ),
        expected_error_fragment=(
            "source query returned multiple rows for the same unique_key (customer_id)"
        ),
    ),
    SnapshotCheckFailureTestCase(
        description="historical check snapshot duplicate identity fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_daily\n"
                "    schema: main\n"
                "    table: raw_customer_daily\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [plan],\n"
                "  observed_at observed_at\n"
                ");\n\n"
                'SELECT customer_id, plan, observed_at FROM __source("raw_customer_daily")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customer_daily AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at "
            "UNION ALL SELECT 1 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-01' AS observed_at",
        ),
        expected_error_fragment=(
            "source query returned multiple rows for the same snapshot identity "
            "(customer_id, observed_at)"
        ),
    ),
    SnapshotCheckFailureTestCase(
        description="check snapshot missing check column fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status]\n"
                ");\n\n"
                'SELECT customer_id, plan FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status",
        ),
        expected_error_fragment="query output is missing required columns: status",
    ),
    SnapshotCheckFailureTestCase(
        description="check snapshot wildcard check columns are not treated as supported",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [*]\n"
                ");\n\n"
                'SELECT customer_id, status FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS SELECT 1 AS customer_id, 'active' AS status",
        ),
        expected_error_fragment="query output is missing required columns: *",
    ),
    SnapshotCheckFailureTestCase(
        description="check snapshot missing one of multiple check columns fails clearly",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status, tier]\n"
                ");\n\n"
                'SELECT customer_id, status FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'active' AS status, 'bronze' AS tier",
        ),
        expected_error_fragment="query output is missing required columns: tier",
    ),
]

SNAPSHOT_HARD_DELETE_TEST_CASES: list[SnapshotHardDeleteExecutionTestCase] = [
    SnapshotHardDeleteExecutionTestCase(
        description="timestamp snapshot closes missing source rows when hard deletes are enabled",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  invalidate_hard_deletes true\n"
                ");\n\n"
                'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
            "UNION ALL SELECT 2 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        ),
        delete_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'team' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at "
            "UNION ALL SELECT 3 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-04 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, plan, valid_to IS NULL FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_to IS NULL, plan"
        ),
        expected_initial_rows=((1, "basic", True), (2, "pro", True)),
        expected_deleted_rows=(
            (1, "basic", False),
            (1, "team", True),
            (2, "pro", False),
            (3, "basic", True),
        ),
    ),
    SnapshotHardDeleteExecutionTestCase(
        description="check snapshot closes missing source rows when hard deletes are enabled",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy check,\n"
                "  check_columns [status],\n"
                "  invalidate_hard_deletes true\n"
                ");\n\n"
                'SELECT customer_id, plan, status FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status "
            "UNION ALL SELECT 2 AS customer_id, 'pro' AS plan, 'active' AS status",
        ),
        delete_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, 'paused' AS status "
            "UNION ALL SELECT 3 AS customer_id, 'basic' AS plan, 'active' AS status",
        ),
        expected_query=(
            "SELECT customer_id, plan, status, valid_to IS NULL FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_to IS NULL, status"
        ),
        expected_initial_rows=((1, "basic", "active", True), (2, "pro", "active", True)),
        expected_deleted_rows=(
            (1, "basic", "active", False),
            (1, "basic", "paused", True),
            (2, "pro", "active", False),
            (3, "basic", "active", True),
        ),
    ),
    SnapshotHardDeleteExecutionTestCase(
        description="timestamp snapshot leaves missing rows active by default",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
            "UNION ALL SELECT 2 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        ),
        delete_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, plan, valid_to IS NULL FROM main.customer_snapshot "
            "ORDER BY customer_id"
        ),
        expected_initial_rows=((1, "basic", True), (2, "pro", True)),
        expected_deleted_rows=((1, "basic", True), (2, "pro", True)),
    ),
    SnapshotHardDeleteExecutionTestCase(
        description="timestamp snapshot leaves missing rows active when hard deletes are false",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  invalidate_hard_deletes false\n"
                ");\n\n"
                'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
            "UNION ALL SELECT 2 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        ),
        delete_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, plan, valid_to IS NULL FROM main.customer_snapshot "
            "ORDER BY customer_id"
        ),
        expected_initial_rows=((1, "basic", True), (2, "pro", True)),
        expected_deleted_rows=((1, "basic", True), (2, "pro", True)),
    ),
    SnapshotHardDeleteExecutionTestCase(
        description="hard deletes use configured validity column names",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  invalidate_hard_deletes true,\n"
                "  valid_from_column effective_from,\n"
                "  valid_to_column effective_to\n"
                ");\n\n"
                'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
            "UNION ALL SELECT 2 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        ),
        delete_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, plan, effective_to IS NULL FROM main.customer_snapshot "
            "ORDER BY customer_id"
        ),
        expected_initial_rows=((1, "basic", True), (2, "pro", True)),
        expected_deleted_rows=((1, "basic", True), (2, "pro", False)),
    ),
    SnapshotHardDeleteExecutionTestCase(
        description="hard deletes respect composite unique keys",
        model_name="customer_region_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_regions\n"
                "    schema: main\n"
                "    table: raw_customer_regions\n"
            ),
            "models/customer_region_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id, region],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at,\n"
                "  invalidate_hard_deletes true\n"
                ");\n\n"
                "SELECT customer_id, region, plan, updated_at "
                'FROM __source("raw_customer_regions")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        delete_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, region, plan, valid_to IS NULL "
            "FROM main.customer_region_snapshot ORDER BY region"
        ),
        expected_initial_rows=((1, "eu", "basic", True), (1, "us", "basic", True)),
        expected_deleted_rows=((1, "eu", "basic", False), (1, "us", "basic", True)),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_TIMESTAMP_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_TIMESTAMP_TEST_CASES],
)
def test_given_current_state_timestamp_snapshot_when_building_then_tracks_history(
    test_case: SnapshotTimestampExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    build_case: BuildExecutionTestCase = BuildExecutionTestCase(
        description=test_case.description,
        project_files=test_case.project_files,
        setup_sql=test_case.initial_setup_sql,
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
    )

    initial_result: BuildExecutionResult = run_build_for_project(
        test_case=build_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_initial: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    unchanged_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_unchanged: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    for sql in test_case.stale_setup_sql:
        connection.execute(sql)
    stale_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_stale: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    sql: str
    for sql in test_case.changed_setup_sql:
        connection.execute(sql)
    changed_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert initial_result.status == BuildStatus.SUCCESS
    assert unchanged_result.status == BuildStatus.SUCCESS
    assert stale_result.status == BuildStatus.SUCCESS
    assert changed_result.status == BuildStatus.SUCCESS
    verify_model_statuses(result=initial_result, test_case=build_case)
    verify_model_statuses(result=unchanged_result, test_case=build_case)
    verify_model_statuses(result=stale_result, test_case=build_case)
    verify_model_statuses(result=changed_result, test_case=build_case)
    validity_columns: tuple[str, ...] = tuple(
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{test_case.model_name}' "
            f"AND column_name IN {test_case.expected_validity_columns} ORDER BY ordinal_position"
        ).fetchall()
    )
    rows_after_changed: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    assert validity_columns == test_case.expected_validity_columns
    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_unchanged == test_case.expected_initial_rows
    assert rows_after_stale == test_case.expected_stale_rows
    assert rows_after_changed == test_case.expected_changed_rows


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_HISTORICAL_TIMESTAMP_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_HISTORICAL_TIMESTAMP_TEST_CASES],
)
def test_given_historical_timestamp_snapshot_when_building_then_uses_updated_history(
    test_case: SnapshotHistoricalTimestampExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    initial_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            setup_sql=test_case.initial_setup_sql,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_initial: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )

    sql: str
    for sql in test_case.changed_setup_sql:
        connection.execute(sql)
    changed_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_changed: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )

    assert initial_result.status == BuildStatus.SUCCESS
    assert changed_result.status == BuildStatus.SUCCESS
    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_changed == test_case.expected_changed_rows


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_TIMESTAMP_FAILURE_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_TIMESTAMP_FAILURE_TEST_CASES],
)
def test_given_invalid_timestamp_snapshot_source_when_building_then_fails_before_target_mutation(
    test_case: SnapshotTimestampFailureTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            setup_sql=test_case.setup_sql,
            expected_status=BuildStatus.FAILED,
            expected_failure_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.FAILED),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert result.status == BuildStatus.FAILED
    assert result.failure_count == 1
    verify_model_statuses(
        result=result,
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.FAILED,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.FAILED),),
        ),
    )
    assert test_case.expected_error_fragment in (result.model_results[0].error_message or "")
    target_exists: bool = (
        connection.execute(
            f"SELECT 1 FROM information_schema.tables WHERE table_name = '{test_case.model_name}'"
        ).fetchone()
        is not None
    )
    assert target_exists is False


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_CHECK_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_CHECK_TEST_CASES],
)
def test_given_current_state_check_snapshot_when_building_then_tracks_checked_changes(
    test_case: SnapshotCheckExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    build_case: BuildExecutionTestCase = BuildExecutionTestCase(
        description=test_case.description,
        project_files=test_case.project_files,
        setup_sql=test_case.initial_setup_sql,
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
    )

    initial_result: BuildExecutionResult = run_build_for_project(
        test_case=build_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_initial: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    for sql in test_case.unchecked_setup_sql:
        connection.execute(sql)
    unchecked_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_unchecked: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    for sql in test_case.checked_setup_sql:
        connection.execute(sql)
    checked_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert initial_result.status == BuildStatus.SUCCESS
    assert unchecked_result.status == BuildStatus.SUCCESS
    assert checked_result.status == BuildStatus.SUCCESS
    verify_model_statuses(result=initial_result, test_case=build_case)
    verify_model_statuses(result=unchecked_result, test_case=build_case)
    verify_model_statuses(result=checked_result, test_case=build_case)
    validity_columns: tuple[str, ...] = tuple(
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{test_case.model_name}' "
            f"AND column_name IN {test_case.expected_validity_columns} ORDER BY ordinal_position"
        ).fetchall()
    )
    rows_after_checked: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    assert validity_columns == test_case.expected_validity_columns
    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_unchecked == test_case.expected_unchecked_rows
    assert rows_after_checked == test_case.expected_checked_rows


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_HISTORICAL_CHECK_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_HISTORICAL_CHECK_TEST_CASES],
)
def test_given_historical_check_snapshot_when_building_then_tracks_observed_history(
    test_case: SnapshotHistoricalCheckExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    initial_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            setup_sql=test_case.initial_setup_sql,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_initial: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )

    for sql in test_case.changed_setup_sql:
        connection.execute(sql)
    changed_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_changed: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )

    assert initial_result.status == BuildStatus.SUCCESS
    assert changed_result.status == BuildStatus.SUCCESS
    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_changed == test_case.expected_changed_rows


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_CHECK_FAILURE_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_CHECK_FAILURE_TEST_CASES],
)
def test_given_invalid_check_snapshot_source_when_building_then_fails_before_target_mutation(
    test_case: SnapshotCheckFailureTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            setup_sql=test_case.setup_sql,
            expected_status=BuildStatus.FAILED,
            expected_failure_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.FAILED),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert result.status == BuildStatus.FAILED
    assert result.failure_count == 1
    verify_model_statuses(
        result=result,
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.FAILED,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.FAILED),),
        ),
    )
    assert test_case.expected_error_fragment in (result.model_results[0].error_message or "")
    target_exists: bool = (
        connection.execute(
            f"SELECT 1 FROM information_schema.tables WHERE table_name = '{test_case.model_name}'"
        ).fetchone()
        is not None
    )
    assert target_exists is False


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_HARD_DELETE_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_HARD_DELETE_TEST_CASES],
)
def test_given_current_state_snapshot_when_source_row_disappears_then_hard_delete_policy_applies(
    test_case: SnapshotHardDeleteExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    initial_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            setup_sql=test_case.initial_setup_sql,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_initial: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    sql: str
    for sql in test_case.delete_setup_sql:
        connection.execute(sql)
    deleted_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_deleted: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )

    assert initial_result.status == BuildStatus.SUCCESS
    assert deleted_result.status == BuildStatus.SUCCESS
    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_deleted == test_case.expected_deleted_rows


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotHardDeleteExecutionTestCase(
            description="hard deletes do not run when duplicate source keys fail validation",
            model_name="customer_snapshot",
            project_files={
                "sqlbuild_project.toml": _PROJECT_YML,
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_customers\n"
                    "    schema: main\n"
                    "    table: raw_customers\n"
                ),
                "models/customer_snapshot.sql": (
                    "MODEL (\n"
                    "  materialized snapshot,\n"
                    "  unique_key [customer_id],\n"
                    "  snapshot_strategy timestamp,\n"
                    "  updated_at updated_at,\n"
                    "  invalidate_hard_deletes true\n"
                    ");\n\n"
                    'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
                ),
            },
            initial_setup_sql=(
                "CREATE TABLE main.raw_customers AS "
                "SELECT 1 AS customer_id, 'basic' AS plan, "
                "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
                "UNION ALL SELECT 2 AS customer_id, 'pro' AS plan, "
                "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
            ),
            delete_setup_sql=(
                "CREATE OR REPLACE TABLE main.raw_customers AS "
                "SELECT 1 AS customer_id, 'basic' AS plan, "
                "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
                "UNION ALL SELECT 1 AS customer_id, 'team' AS plan, "
                "TIMESTAMP '2024-01-03 00:00:00' AS updated_at",
            ),
            expected_query=(
                "SELECT customer_id, plan, valid_to IS NULL FROM main.customer_snapshot "
                "ORDER BY customer_id"
            ),
            expected_initial_rows=((1, "basic", True), (2, "pro", True)),
            expected_deleted_rows=((1, "basic", True), (2, "pro", True)),
        )
    ],
    ids=["hard deletes do not run when duplicate source keys fail validation"],
)
def test_given_hard_delete_snapshot_when_duplicate_keys_fail_then_target_history_is_unchanged(
    test_case: SnapshotHardDeleteExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    initial_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            setup_sql=test_case.initial_setup_sql,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    sql: str
    for sql in test_case.delete_setup_sql:
        connection.execute(sql)
    failed_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.FAILED,
            expected_failure_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.FAILED),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_failed_run: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )

    assert initial_result.status == BuildStatus.SUCCESS
    assert failed_result.status == BuildStatus.FAILED
    assert rows_after_failed_run == test_case.expected_deleted_rows


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="check snapshot initial_valid_from can use updated_at",
            project_files={
                "sqlbuild_project.toml": _PROJECT_YML,
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_customers\n"
                    "    schema: main\n"
                    "    table: raw_customers\n"
                ),
                "models/customer_snapshot.sql": (
                    "MODEL (\n"
                    "  materialized snapshot,\n"
                    "  unique_key [customer_id],\n"
                    "  snapshot_strategy check,\n"
                    "  check_columns [status],\n"
                    "  updated_at updated_at,\n"
                    "  initial_valid_from updated_at\n"
                    ");\n\n"
                    'SELECT customer_id, status, updated_at FROM __source("raw_customers")'
                ),
            },
            setup_sql=(
                "CREATE TABLE main.raw_customers AS "
                "SELECT 1 AS customer_id, 'active' AS status, "
                "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
            ),
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=(("customer_snapshot", ExecutionStatus.SUCCESS),),
            expected_query_results=(
                (
                    "SELECT customer_id, status, CAST(valid_from AS VARCHAR), valid_to "
                    "FROM main.customer_snapshot",
                    ((1, "active", "2024-01-01 00:00:00", None),),
                ),
            ),
        )
    ],
    ids=["check snapshot initial_valid_from can use updated_at"],
)
def test_given_check_snapshot_with_initial_valid_from_when_building_then_uses_configured_source(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query_results[0][0]).fetchall()
    )

    assert result.status == test_case.expected_status
    verify_model_statuses(result=result, test_case=test_case)
    assert rows == test_case.expected_query_results[0][1]


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="timestamp snapshot initial_valid_from can explicitly use updated_at",
            project_files={
                "sqlbuild_project.toml": _PROJECT_YML,
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_customers\n"
                    "    schema: main\n"
                    "    table: raw_customers\n"
                ),
                "models/customer_snapshot.sql": (
                    "MODEL (\n"
                    "  materialized snapshot,\n"
                    "  unique_key [customer_id],\n"
                    "  snapshot_strategy timestamp,\n"
                    "  updated_at updated_at,\n"
                    "  initial_valid_from updated_at\n"
                    ");\n\n"
                    'SELECT customer_id, updated_at FROM __source("raw_customers")'
                ),
            },
            setup_sql=(
                "CREATE TABLE main.raw_customers AS "
                "SELECT 1 AS customer_id, TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
            ),
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=(("customer_snapshot", ExecutionStatus.SUCCESS),),
            expected_query_results=(
                (
                    "SELECT customer_id, CAST(valid_from AS VARCHAR), valid_to "
                    "FROM main.customer_snapshot",
                    ((1, "2024-01-01 00:00:00", None),),
                ),
            ),
        )
    ],
    ids=["timestamp snapshot initial_valid_from can explicitly use updated_at"],
)
def test_given_timestamp_snapshot_with_updated_at_initial_validity_when_building_then_uses_cursor(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query_results[0][0]).fetchall()
    )

    assert result.status == test_case.expected_status
    verify_model_statuses(result=result, test_case=test_case)
    assert rows == test_case.expected_query_results[0][1]


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="timestamp snapshot initial_valid_from can use execution time",
            project_files={
                "sqlbuild_project.toml": _PROJECT_YML,
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_customers\n"
                    "    schema: main\n"
                    "    table: raw_customers\n"
                ),
                "models/customer_snapshot.sql": (
                    "MODEL (\n"
                    "  materialized snapshot,\n"
                    "  unique_key [customer_id],\n"
                    "  snapshot_strategy timestamp,\n"
                    "  updated_at updated_at,\n"
                    "  initial_valid_from execution_time\n"
                    ");\n\n"
                    'SELECT customer_id, updated_at FROM __source("raw_customers")'
                ),
            },
            setup_sql=(
                "CREATE TABLE main.raw_customers AS "
                "SELECT 1 AS customer_id, TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
            ),
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=(("customer_snapshot", ExecutionStatus.SUCCESS),),
            expected_query_results=(
                (
                    "SELECT customer_id, valid_from > updated_at, valid_to IS NULL "
                    "FROM main.customer_snapshot",
                    ((1, True, True),),
                ),
            ),
        )
    ],
    ids=["timestamp snapshot initial_valid_from can use execution time"],
)
def test_given_timestamp_snapshot_with_execution_initial_validity_when_building_then_uses_run_time(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query_results[0][0]).fetchall()
    )

    assert result.status == test_case.expected_status
    verify_model_statuses(result=result, test_case=test_case)
    assert rows == test_case.expected_query_results[0][1]


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="check snapshot explicitly accepts execution-time initial validity",
            project_files={
                "sqlbuild_project.toml": _PROJECT_YML,
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_customers\n"
                    "    schema: main\n"
                    "    table: raw_customers\n"
                ),
                "models/customer_snapshot.sql": (
                    "MODEL (\n"
                    "  materialized snapshot,\n"
                    "  unique_key [customer_id],\n"
                    "  snapshot_strategy check,\n"
                    "  check_columns [status],\n"
                    "  updated_at updated_at,\n"
                    "  initial_valid_from execution_time\n"
                    ");\n\n"
                    'SELECT customer_id, status, updated_at FROM __source("raw_customers")'
                ),
            },
            setup_sql=(
                "CREATE TABLE main.raw_customers AS "
                "SELECT 1 AS customer_id, 'active' AS status, "
                "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
            ),
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=(("customer_snapshot", ExecutionStatus.SUCCESS),),
            expected_query_results=(
                (
                    "SELECT customer_id, valid_from > updated_at, valid_to IS NULL "
                    "FROM main.customer_snapshot",
                    ((1, True, True),),
                ),
            ),
        )
    ],
    ids=["check snapshot explicitly accepts execution-time initial validity"],
)
def test_given_check_snapshot_with_execution_initial_validity_when_building_then_uses_run_time(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query_results[0][0]).fetchall()
    )

    assert result.status == test_case.expected_status
    verify_model_statuses(result=result, test_case=test_case)
    assert rows == test_case.expected_query_results[0][1]


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="planner carries initial_valid_from into snapshot plan entries",
            project_files={
                "sqlbuild_project.toml": _PROJECT_YML,
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_customers\n"
                    "    schema: main\n"
                    "    table: raw_customers\n"
                ),
                "models/customer_snapshot.sql": (
                    "MODEL (\n"
                    "  materialized snapshot,\n"
                    "  unique_key [customer_id],\n"
                    "  snapshot_strategy timestamp,\n"
                    "  updated_at updated_at,\n"
                    "  initial_valid_from execution_time\n"
                    ");\n\n"
                    'SELECT customer_id, updated_at FROM __source("raw_customers")'
                ),
            },
            expected_status=BuildStatus.SUCCESS,
            expected_model_statuses=(("customer_snapshot", ExecutionStatus.SUCCESS),),
        )
    ],
    ids=["planner carries initial_valid_from into snapshot plan entries"],
)
def test_given_snapshot_initial_validity_config_when_planning_then_plan_entry_preserves_value(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered,
        adapter=adapter,
        no_sql_validation=True,
    )
    plan: PlanOutput = pipeline_result.plan_output
    entry: ModelPlanEntry = plan.model_entries[0]

    assert entry.name == test_case.expected_model_statuses[0][0]
    assert entry.initial_valid_from == "execution_time"


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="check snapshot runs final column audits",
            project_files={
                "sqlbuild_project.toml": _PROJECT_YML,
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_customers\n"
                    "    schema: main\n"
                    "    table: raw_customers\n"
                ),
                "models/customer_snapshot.sql": (
                    "MODEL (\n"
                    "  materialized snapshot,\n"
                    "  unique_key [customer_id],\n"
                    "  snapshot_strategy check,\n"
                    "  check_columns [status],\n"
                    "  columns (customer_id (audits [not_null]))\n"
                    ");\n\n"
                    'SELECT customer_id, status FROM __source("raw_customers")'
                ),
                "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
            },
            setup_sql=(
                "CREATE TABLE main.raw_customers AS SELECT 1 AS customer_id, 'active' AS status",
            ),
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=(("customer_snapshot", ExecutionStatus.SUCCESS),),
            expected_model_audit_count=1,
            expected_query_results=(
                (
                    "SELECT customer_id, status, valid_to IS NULL FROM main.customer_snapshot",
                    ((1, "active", True),),
                ),
            ),
        )
    ],
    ids=["check snapshot runs final column audits"],
)
def test_given_check_snapshot_with_final_audit_when_building_then_runs_audit(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert result.status == test_case.expected_status
    assert result.success_count == test_case.expected_success_count
    verify_model_statuses(result=result, test_case=test_case)
    assert sum(len(model_result.audit_results) for model_result in result.model_results) == (
        test_case.expected_model_audit_count
    )
    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        actual_rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row) for row in connection.execute(query).fetchall()
        )
        assert actual_rows == expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="check snapshot final audit failure fails after target update",
            project_files={
                "sqlbuild_project.toml": _PROJECT_YML,
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_customers\n"
                    "    schema: main\n"
                    "    table: raw_customers\n"
                ),
                "models/customer_snapshot.sql": (
                    "MODEL (\n"
                    "  materialized snapshot,\n"
                    "  unique_key [customer_id],\n"
                    "  snapshot_strategy check,\n"
                    "  check_columns [status],\n"
                    "  columns (customer_id (audits [not_null]))\n"
                    ");\n\n"
                    'SELECT customer_id, status FROM __source("raw_customers")'
                ),
                "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
            },
            setup_sql=(
                "CREATE TABLE main.raw_customers AS "
                "SELECT NULL::INTEGER AS customer_id, 'active' AS status",
            ),
            expected_status=BuildStatus.FAILED,
            expected_failure_count=1,
            expected_model_statuses=(("customer_snapshot", ExecutionStatus.FAILED),),
            expected_model_audit_count=1,
            expected_query_results=(
                (
                    "SELECT customer_id, status, valid_to IS NULL FROM main.customer_snapshot",
                    ((None, "active", True),),
                ),
            ),
        )
    ],
    ids=["check snapshot final audit failure fails after target update"],
)
def test_given_check_snapshot_with_failing_final_audit_when_building_then_fails_after_update(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert result.status == test_case.expected_status
    assert result.failure_count == test_case.expected_failure_count
    verify_model_statuses(result=result, test_case=test_case)
    assert sum(len(model_result.audit_results) for model_result in result.model_results) == (
        test_case.expected_model_audit_count
    )
    assert result.model_results[0].error_message is not None
    assert "final audit for 'customer_snapshot' failed after target update" in (
        result.model_results[0].error_message
    )
    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        actual_rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row) for row in connection.execute(query).fetchall()
        )
        assert actual_rows == expected_rows
