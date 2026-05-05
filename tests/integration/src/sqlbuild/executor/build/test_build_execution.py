"""Integration tests for build plan execution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.build._test_types import (
    BuildExecutionTestCase,
)
from tests.integration.src.sqlbuild.executor.build.helpers import (
    run_build_for_project,
    verify_audit_counts,
    verify_model_statuses,
    verify_test_counts,
    verify_warehouse_state,
)

_PROJECT_YML: str = (
    "name: demo\n"
    "adapter: duckdb\n"
    "connection:\n"
    "  database: ':memory:'\n"
    "settings:\n"
    "  default_audit_severity: error\n"
)

_PROJECT_YML_WARN: str = (
    "name: demo\n"
    "adapter: duckdb\n"
    "connection:\n"
    "  database: ':memory:'\n"
    "settings:\n"
    "  default_audit_severity: warn\n"
)

_PROJECT_YML_DIRECT: str = (
    "name: demo\n"
    "adapter: duckdb\n"
    "connection:\n"
    "  database: ':memory:'\n"
    "settings:\n"
    "  default_audit_severity: error\n"
    "  table_promotion_mode: direct\n"
)

_NOT_NULL_AUDIT: str = 'AUDIT ();\n\nSELECT @column FROM __ref("@model") WHERE @column IS NULL'

_PASSING_TEST_SQL: str = (
    "TEST ();\n\n"
    "WITH\n"
    "__ref__stg_orders AS (\n"
    "  SELECT 1 AS id, 'alice' AS name\n"
    "),\n"
    "__expected__stg_orders AS (\n"
    "  SELECT 1 AS id, 'alice' AS name\n"
    ")\n"
    "SELECT 1\n"
)

_FAILING_TEST_SQL: str = (
    "TEST ();\n\n"
    "WITH\n"
    "__ref__stg_orders AS (\n"
    "  SELECT 1 AS id, 'alice' AS name\n"
    "),\n"
    "__expected__stg_orders AS (\n"
    "  SELECT 1 AS id, 'wrong_name' AS name\n"
    ")\n"
    "SELECT 1\n"
)

SUCCESS_TEST_CASES: list[BuildExecutionTestCase] = [
    BuildExecutionTestCase(
        description="sql udf builds before dependent model",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "functions/sql/is_positive_int.sql": (
                "FUNCTION (\n"
                "  arguments (a_string VARCHAR),\n"
                "  returns BOOLEAN\n"
                ");\n\n"
                "regexp_matches(a_string, '^[0-9]+$')"
            ),
            "models/validated_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT value, __udf("is_positive_int")(value) AS is_positive '
                "FROM (VALUES ('123'), ('abc')) AS input(value)"
            ),
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=2,
        expected_model_statuses=(("validated_orders", ExecutionStatus.SUCCESS),),
        expected_query_results=(
            (
                "SELECT value, is_positive FROM main.validated_orders ORDER BY value DESC",
                (("abc", False), ("123", True)),
            ),
        ),
    ),
    BuildExecutionTestCase(
        description="two independent models both succeed",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id, 'alice' AS name",
            "models/payments.sql": (
                "MODEL (materialized table);\n\nSELECT 10 AS payment_id, 500 AS amount"
            ),
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=2,
        expected_model_statuses=(
            ("orders", ExecutionStatus.SUCCESS),
            ("payments", ExecutionStatus.SUCCESS),
        ),
        expected_query_results=(
            ("SELECT id, name FROM main.orders", ((1, "alice"),)),
            ("SELECT payment_id, amount FROM main.payments", ((10, 500),)),
        ),
    ),
    BuildExecutionTestCase(
        description="dependent models execute in topo order and downstream reads upstream",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (materialized table);\n\nSELECT 42 AS id, 'bob' AS name"
            ),
            "models/orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT id, name FROM __ref("stg_orders") WHERE id = 42'
            ),
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=2,
        expected_model_statuses=(
            ("stg_orders", ExecutionStatus.SUCCESS),
            ("orders", ExecutionStatus.SUCCESS),
        ),
        expected_query_results=(
            ("SELECT id, name FROM main.stg_orders", ((42, "bob"),)),
            ("SELECT id, name FROM main.orders", ((42, "bob"),)),
        ),
    ),
    BuildExecutionTestCase(
        description="environment schema is auto-created during build",
        project_files={
            "sqlbuild_project.yml": (
                "name: demo\n"
                "adapter: duckdb\n"
                "connection:\n"
                "  database: ':memory:'\n"
                "default_environment: dev\n"
                "environments:\n"
                "  dev:\n"
                "    schema: dev_schema\n"
            ),
            "sqlbuild_local.yml": "environment: dev\n",
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id, 'alice' AS name",
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_statuses=(("orders", ExecutionStatus.SUCCESS),),
        expected_query_results=(("SELECT id, name FROM dev_schema.orders", ((1, "alice"),)),),
    ),
    BuildExecutionTestCase(
        description="run_audits false skips all audits but tables still built",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id",
            "models/schema.yml": (
                "models:\n"
                "  - name: orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
        },
        run_audits=False,
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_audit_count=0,
        expected_query_results=(("SELECT id FROM main.orders", ((1,),)),),
    ),
    BuildExecutionTestCase(
        description="passing model audit does not block and table is promoted",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id",
            "models/schema.yml": (
                "models:\n"
                "  - name: orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_audit_count=1,
        expected_query_results=(("SELECT id FROM main.orders", ((1,),)),),
    ),
    BuildExecutionTestCase(
        description="warn audit records warning but build succeeds",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML_WARN,
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT NULL AS id",
            "models/schema.yml": (
                "models:\n"
                "  - name: orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_audit_count=1,
        expected_warning_count=1,
        expected_query_results=(("SELECT id FROM main.orders", ((None,),)),),
    ),
    BuildExecutionTestCase(
        description="source audit warn does not block dependent models",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML_WARN,
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")'
            ),
            "sources/raw.yml": (
                "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            ),
            "audits/singular/source_check.sql": (
                'AUDIT ();\n\nSELECT id FROM __source("raw_orders") WHERE id IS NULL'
            ),
        },
        setup_sql=("CREATE TABLE main.raw_orders AS SELECT NULL AS id",),
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_source_audit_count=1,
        expected_warning_count=1,
        expected_query_results=(("SELECT id FROM main.orders", ((None,),)),),
    ),
    BuildExecutionTestCase(
        description="end audit warn succeeds build with warning",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML_WARN,
            "models/orders.sql": ("MODEL (materialized table);\n\nSELECT 1 AS id"),
            "models/payments.sql": ("MODEL (materialized table);\n\nSELECT 2 AS payment_id"),
            "audits/singular/cross_check.sql": (
                'AUDIT ();\n\nSELECT o.id FROM __ref("orders") o CROSS JOIN __ref("payments") p'
            ),
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=2,
        expected_end_audit_count=1,
        expected_warning_count=1,
        expected_query_results=(
            ("SELECT id FROM main.orders", ((1,),)),
            ("SELECT payment_id FROM main.payments", ((2,),)),
        ),
    ),
    BuildExecutionTestCase(
        description="run_audits false skips source model and end audits but tables still built",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")'
            ),
            "models/payments.sql": ("MODEL (materialized table);\n\nSELECT 1 AS payment_id"),
            "models/schema.yml": (
                "models:\n"
                "  - name: orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "sources/raw.yml": (
                "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
            "audits/singular/source_check.sql": (
                'AUDIT ();\n\nSELECT id FROM __source("raw_orders") WHERE id IS NULL'
            ),
            "audits/singular/cross_check.sql": (
                'AUDIT ();\n\nSELECT o.id FROM __ref("orders") o CROSS JOIN __ref("payments") p'
            ),
        },
        setup_sql=("CREATE TABLE main.raw_orders AS SELECT NULL AS id",),
        run_audits=False,
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=2,
        expected_model_audit_count=0,
        expected_source_audit_count=0,
        expected_end_audit_count=0,
        expected_query_results=(
            ("SELECT id FROM main.orders", ((None,),)),
            ("SELECT payment_id FROM main.payments", ((1,),)),
        ),
    ),
    BuildExecutionTestCase(
        description="direct mode warn audit records warning and build succeeds",
        project_files={
            "sqlbuild_project.yml": (
                "name: demo\n"
                "adapter: duckdb\n"
                "connection:\n"
                "  database: ':memory:'\n"
                "settings:\n"
                "  default_audit_severity: warn\n"
                "  table_promotion_mode: direct\n"
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT NULL AS id",
            "models/schema.yml": (
                "models:\n"
                "  - name: orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_audit_count=1,
        expected_warning_count=1,
        expected_query_results=(("SELECT id FROM main.orders", ((None,),)),),
    ),
    BuildExecutionTestCase(
        description="build writes fingerprints when query tracking is enabled",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id",
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_query_results=(
            ("SELECT id FROM main.orders", ((1,),)),
            (
                "SELECT model_name FROM main._sqlbuild_fingerprints ORDER BY model_name",
                (("orders",),),
            ),
        ),
    ),
    BuildExecutionTestCase(
        description="direct mode with passing audit creates table",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML_DIRECT,
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 5 AS id",
            "models/schema.yml": (
                "models:\n"
                "  - name: orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_audit_count=1,
        expected_query_results=(("SELECT id FROM main.orders", ((5,),)),),
    ),
]

FAILURE_TEST_CASES: list[BuildExecutionTestCase] = [
    BuildExecutionTestCase(
        description="model failure blocks downstream and blocked table does not exist",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (materialized table);\n\nSELECT * FROM nonexistent_table"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __ref("stg_orders")'
            ),
        },
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_skipped_count=1,
        expected_model_statuses=(
            ("stg_orders", ExecutionStatus.FAILED),
            ("orders", ExecutionStatus.SKIPPED),
        ),
        expected_missing_relations=("main.stg_orders", "main.orders"),
    ),
    BuildExecutionTestCase(
        description="independent branch succeeds with real data despite sibling failure",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (materialized table);\n\nSELECT * FROM nonexistent_table"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __ref("stg_orders")'
            ),
            "models/payments.sql": (
                "MODEL (materialized table);\n\nSELECT 99 AS payment_id, 750 AS amount"
            ),
        },
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_skipped_count=1,
        expected_success_count=1,
        expected_model_statuses=(
            ("stg_orders", ExecutionStatus.FAILED),
            ("orders", ExecutionStatus.SKIPPED),
            ("payments", ExecutionStatus.SUCCESS),
        ),
        expected_query_results=(("SELECT payment_id, amount FROM main.payments", ((99, 750),)),),
        expected_missing_relations=("main.stg_orders", "main.orders"),
    ),
    BuildExecutionTestCase(
        description="failing error audit blocks promotion and table has no final data",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT NULL AS id",
            "models/schema.yml": (
                "models:\n"
                "  - name: orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
        },
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_model_audit_count=1,
        expected_model_statuses=(("orders", ExecutionStatus.FAILED),),
        expected_missing_relations=("main.orders",),
    ),
    BuildExecutionTestCase(
        description="end audit error fails build but completed tables are preserved",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": ("MODEL (materialized table);\n\nSELECT 7 AS id, 'carol' AS name"),
            "models/payments.sql": ("MODEL (materialized table);\n\nSELECT 1 AS payment_id"),
            "audits/singular/cross_check.sql": (
                'AUDIT ();\n\nSELECT o.id FROM __ref("orders") o CROSS JOIN __ref("payments") p'
            ),
        },
        expected_status=BuildStatus.FAILED,
        expected_success_count=2,
        expected_end_audit_count=1,
        expected_query_results=(
            ("SELECT id, name FROM main.orders", ((7, "carol"),)),
            ("SELECT payment_id FROM main.payments", ((1,),)),
        ),
    ),
    BuildExecutionTestCase(
        description="fail_fast stops after first failure and second model never materialized",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/aaa_broken.sql": (
                "MODEL (materialized table);\n\nSELECT * FROM nonexistent_table"
            ),
            "models/zzz_healthy.sql": ("MODEL (materialized table);\n\nSELECT 1 AS id"),
        },
        fail_fast=True,
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_success_count=0,
        expected_skipped_count=1,
        expected_missing_relations=("main.aaa_broken", "main.zzz_healthy"),
    ),
    BuildExecutionTestCase(
        description="source audit error blocks dependent models and tables do not exist",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")'
            ),
            "sources/raw.yml": (
                "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            ),
            "audits/singular/source_check.sql": (
                'AUDIT ();\n\nSELECT id FROM __source("raw_orders") WHERE id IS NULL'
            ),
        },
        setup_sql=("CREATE TABLE main.raw_orders AS SELECT NULL AS id",),
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_skipped_count=1,
        expected_source_audit_count=1,
        expected_model_statuses=(("orders", ExecutionStatus.SKIPPED),),
        expected_missing_relations=("main.orders",),
    ),
    BuildExecutionTestCase(
        description="source audit error transitively blocks entire dependent chain",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")'
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __ref("stg_orders")'
            ),
            "sources/raw.yml": (
                "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            ),
            "audits/singular/source_check.sql": (
                'AUDIT ();\n\nSELECT id FROM __source("raw_orders") WHERE id IS NULL'
            ),
        },
        setup_sql=("CREATE TABLE main.raw_orders AS SELECT NULL AS id",),
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_skipped_count=2,
        expected_source_audit_count=1,
        expected_model_statuses=(
            ("stg_orders", ExecutionStatus.SKIPPED),
            ("orders", ExecutionStatus.SKIPPED),
        ),
        expected_missing_relations=("main.stg_orders", "main.orders"),
    ),
    BuildExecutionTestCase(
        description="direct mode failing audit leaves target updated but build fails",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML_DIRECT,
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT NULL AS id",
            "models/schema.yml": (
                "models:\n"
                "  - name: orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
        },
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_model_audit_count=1,
        expected_model_statuses=(("orders", ExecutionStatus.FAILED),),
        expected_query_results=(("SELECT id FROM main.orders", ((None,),)),),
    ),
    BuildExecutionTestCase(
        description="pre_hook failure blocks model and downstream table does not exist",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (\n  materialized table\n  pre_hook 'INVALID SQL STATEMENT'\n);\n\n"
                "SELECT 1 AS id"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __ref("stg_orders")'
            ),
        },
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_skipped_count=1,
        expected_model_statuses=(
            ("stg_orders", ExecutionStatus.FAILED),
            ("orders", ExecutionStatus.SKIPPED),
        ),
        expected_missing_relations=("main.stg_orders", "main.orders"),
    ),
    BuildExecutionTestCase(
        description="post_hook failure blocks downstream but failed model table exists",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (\n  materialized table\n  post_hook 'INVALID SQL STATEMENT'\n);\n\n"
                "SELECT 88 AS id"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __ref("stg_orders")'
            ),
        },
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_skipped_count=1,
        expected_model_statuses=(
            ("stg_orders", ExecutionStatus.FAILED),
            ("orders", ExecutionStatus.SKIPPED),
        ),
        expected_query_results=(("SELECT id FROM main.stg_orders", ((88,),)),),
        expected_missing_relations=("main.orders",),
    ),
    BuildExecutionTestCase(
        description="two independent failures both recorded in non fail_fast",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/broken_a.sql": ("MODEL (materialized table);\n\nSELECT * FROM nonexistent_a"),
            "models/broken_b.sql": ("MODEL (materialized table);\n\nSELECT * FROM nonexistent_b"),
        },
        expected_status=BuildStatus.FAILED,
        expected_failure_count=2,
        expected_success_count=0,
        expected_model_statuses=(
            ("broken_a", ExecutionStatus.FAILED),
            ("broken_b", ExecutionStatus.FAILED),
        ),
        expected_missing_relations=("main.broken_a", "main.broken_b"),
    ),
    BuildExecutionTestCase(
        description="staged audit failure preserves existing target with old data",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT NULL AS id",
            "models/schema.yml": (
                "models:\n"
                "  - name: orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
        },
        setup_sql=("CREATE TABLE main.orders AS SELECT 999 AS id",),
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_model_audit_count=1,
        expected_model_statuses=(("orders", ExecutionStatus.FAILED),),
        expected_query_results=(("SELECT id FROM main.orders", ((999,),)),),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SUCCESS_TEST_CASES,
    ids=[case.description for case in SUCCESS_TEST_CASES],
)
def test_given_build_plan_when_executing_then_succeeds(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case, project_dir=tmp_path, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    assert result.success_count == test_case.expected_success_count
    assert result.failure_count == test_case.expected_failure_count
    assert result.skipped_count == test_case.expected_skipped_count
    verify_model_statuses(result=result, test_case=test_case)
    verify_audit_counts(result=result, test_case=test_case)
    verify_warehouse_state(connection=connection, test_case=test_case)


VIEW_SUCCESS_TEST_CASES: list[BuildExecutionTestCase] = [
    BuildExecutionTestCase(
        description="view model creates view and downstream table reads it",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (materialized view);\n\nSELECT 1 AS id, 'alice' AS name"
            ),
            "models/dim_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id, name FROM __ref("stg_orders")'
            ),
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=2,
        expected_model_statuses=(
            ("stg_orders", ExecutionStatus.SUCCESS),
            ("dim_orders", ExecutionStatus.SUCCESS),
        ),
        expected_query_results=(("SELECT id, name FROM main.dim_orders", ((1, "alice"),)),),
    ),
    BuildExecutionTestCase(
        description="view with audit succeeds when audit passes",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (materialized view);\n\nSELECT 1 AS id, 'alice' AS name"
            ),
            "models/schema.yml": (
                "models:\n"
                "  - name: stg_orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        audits:\n"
                "          - not_null\n"
            ),
            "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_audit_count=1,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    VIEW_SUCCESS_TEST_CASES,
    ids=[case.description for case in VIEW_SUCCESS_TEST_CASES],
)
def test_given_view_build_plan_when_executing_then_succeeds(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case, project_dir=tmp_path, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    assert result.success_count == test_case.expected_success_count
    verify_model_statuses(result=result, test_case=test_case)
    verify_audit_counts(result=result, test_case=test_case)
    verify_warehouse_state(connection=connection, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="view failure blocks downstream table",
            project_files={
                "sqlbuild_project.yml": _PROJECT_YML,
                "models/bad_view.sql": (
                    "MODEL (materialized view);\n\nSELECT * FROM nonexistent_source_table"
                ),
                "models/downstream.sql": (
                    'MODEL (materialized table);\n\nSELECT * FROM __ref("bad_view")'
                ),
            },
            expected_status=BuildStatus.FAILED,
            expected_failure_count=1,
            expected_skipped_count=1,
            expected_model_statuses=(
                ("bad_view", ExecutionStatus.FAILED),
                ("downstream", ExecutionStatus.SKIPPED),
            ),
            expected_missing_relations=("main.downstream",),
        ),
    ],
    ids=["view failure blocks downstream table"],
)
def test_given_view_build_plan_when_executing_then_fails(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case, project_dir=tmp_path, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    assert result.failure_count == test_case.expected_failure_count
    assert result.skipped_count == test_case.expected_skipped_count
    verify_model_statuses(result=result, test_case=test_case)
    verify_warehouse_state(connection=connection, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="view with run_audits false still creates view",
            project_files={
                "sqlbuild_project.yml": _PROJECT_YML,
                "models/stg_orders.sql": (
                    "MODEL (materialized view);\n\nSELECT 1 AS id, 'alice' AS name"
                ),
                "models/schema.yml": (
                    "models:\n"
                    "  - name: stg_orders\n"
                    "    columns:\n"
                    "      - name: id\n"
                    "        audits:\n"
                    "          - not_null\n"
                ),
                "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
            },
            run_audits=False,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_audit_count=0,
            expected_query_results=(("SELECT id, name FROM main.stg_orders", ((1, "alice"),)),),
        ),
    ],
    ids=["view with run_audits false still creates view"],
)
def test_given_view_with_run_audits_false_when_executing_then_succeeds(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case, project_dir=tmp_path, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    assert result.success_count == test_case.expected_success_count
    verify_audit_counts(result=result, test_case=test_case)
    verify_warehouse_state(connection=connection, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    FAILURE_TEST_CASES,
    ids=[case.description for case in FAILURE_TEST_CASES],
)
def test_given_build_plan_when_executing_then_fails(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case, project_dir=tmp_path, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    assert result.success_count == test_case.expected_success_count
    assert result.failure_count == test_case.expected_failure_count
    assert result.skipped_count == test_case.expected_skipped_count
    verify_model_statuses(result=result, test_case=test_case)
    verify_audit_counts(result=result, test_case=test_case)
    verify_warehouse_state(connection=connection, test_case=test_case)


SQL_TEST_BUILD_TEST_CASES: list[BuildExecutionTestCase] = [
    BuildExecutionTestCase(
        description="passing unit test allows model to materialize",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (materialized table);\n\nSELECT 1 AS id, 'alice' AS name"
            ),
            "tests/unit/test_stg_orders.sql": _PASSING_TEST_SQL,
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=2,
        expected_test_count=1,
        expected_model_statuses=(("stg_orders", ExecutionStatus.SUCCESS),),
        expected_query_results=(("SELECT id, name FROM main.stg_orders", ((1, "alice"),)),),
    ),
    BuildExecutionTestCase(
        description="failing unit test blocks model materialization",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (materialized table);\n\nSELECT 1 AS id, 'alice' AS name"
            ),
            "tests/unit/test_stg_orders.sql": _FAILING_TEST_SQL,
        },
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_skipped_count=1,
        expected_test_count=1,
        expected_model_statuses=(("stg_orders", ExecutionStatus.SKIPPED),),
        expected_missing_relations=("main.stg_orders",),
    ),
    BuildExecutionTestCase(
        description="run_tests false skips test and model materializes",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (materialized table);\n\nSELECT 1 AS id, 'alice' AS name"
            ),
            "tests/unit/test_stg_orders.sql": _FAILING_TEST_SQL,
        },
        run_tests=False,
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_test_count=0,
        expected_model_statuses=(("stg_orders", ExecutionStatus.SUCCESS),),
        expected_query_results=(("SELECT id, name FROM main.stg_orders", ((1, "alice"),)),),
    ),
    BuildExecutionTestCase(
        description="failing test blocks target model and downstream chain",
        project_files={
            "sqlbuild_project.yml": _PROJECT_YML,
            "models/stg_orders.sql": (
                "MODEL (materialized table);\n\nSELECT 1 AS id, 'alice' AS name"
            ),
            "models/dim_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id, name FROM __ref("stg_orders")'
            ),
            "tests/unit/test_stg_orders.sql": _FAILING_TEST_SQL,
        },
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_skipped_count=2,
        expected_test_count=1,
        expected_model_statuses=(
            ("stg_orders", ExecutionStatus.SKIPPED),
            ("dim_orders", ExecutionStatus.SKIPPED),
        ),
        expected_missing_relations=("main.stg_orders", "main.dim_orders"),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SQL_TEST_BUILD_TEST_CASES,
    ids=[case.description for case in SQL_TEST_BUILD_TEST_CASES],
)
def test_given_sql_test_in_build_when_executing_then_matches_expected(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case, project_dir=tmp_path, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    assert result.success_count == test_case.expected_success_count
    assert result.failure_count == test_case.expected_failure_count
    assert result.skipped_count == test_case.expected_skipped_count
    verify_test_counts(result=result, test_case=test_case)
    verify_model_statuses(result=result, test_case=test_case)
    verify_warehouse_state(connection=connection, test_case=test_case)
