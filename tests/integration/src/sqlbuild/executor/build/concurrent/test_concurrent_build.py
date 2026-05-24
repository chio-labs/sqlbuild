"""Integration tests for concurrent build execution with file-based DuckDB."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.integration.src.sqlbuild.executor.build.concurrent._test_types import (
    ConcurrentBuildTestCase,
)
from tests.integration.src.sqlbuild.executor.build.concurrent.helpers import (
    run_concurrent_build,
    verify_concurrent_warehouse_state,
)

_PROJECT_YML: str = (
    'name = "demo"\n'
    'adapter = "duckdb"\n\n'
    "[connection]\n"
    'database = "test.duckdb"\n\n'
    "[settings]\n"
    'default_audit_severity = "error"\n'
)

SUCCESS_TEST_CASES: list[ConcurrentBuildTestCase] = [
    ConcurrentBuildTestCase(
        description=("two independent tables both materialize with concurrency 2"),
        max_concurrency=2,
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "models/alpha.sql": ("MODEL (materialized table);\n\nSELECT 1 AS id, 'alpha' AS name"),
            "models/beta.sql": ("MODEL (materialized table);\n\nSELECT 2 AS id, 'beta' AS name"),
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=2,
        expected_query_results=(
            (
                "SELECT id, name FROM main.alpha",
                ((1, "alpha"),),
            ),
            (
                "SELECT id, name FROM main.beta",
                ((2, "beta"),),
            ),
        ),
    ),
    ConcurrentBuildTestCase(
        description=("diamond DAG with shared upstream materializes all four nodes correctly"),
        max_concurrency=3,
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "models/staging/stg_raw.sql": (
                "MODEL (materialized view);\n\nSELECT 10 AS id, 'row' AS val"
            ),
            "models/branch_a.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT id, val || '_a' AS val FROM __ref(\"stg_raw\")"
            ),
            "models/branch_b.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT id, val || '_b' AS val FROM __ref(\"stg_raw\")"
            ),
            "models/merged.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT a.id, a.val AS a_val, b.val AS b_val "
                'FROM __ref("branch_a") a '
                'JOIN __ref("branch_b") b ON a.id = b.id'
            ),
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=4,
        expected_query_results=(
            (
                "SELECT id, a_val, b_val FROM main.merged",
                ((10, "row_a", "row_b"),),
            ),
        ),
    ),
    ConcurrentBuildTestCase(
        description=("three-layer chain preserves data flow with concurrency 2"),
        max_concurrency=2,
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "models/layer_1.sql": ("MODEL (materialized table);\n\nSELECT 100 AS val"),
            "models/layer_2.sql": (
                'MODEL (materialized table);\n\nSELECT val * 2 AS val FROM __ref("layer_1")'
            ),
            "models/layer_3.sql": (
                'MODEL (materialized table);\n\nSELECT val + 1 AS val FROM __ref("layer_2")'
            ),
        },
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=3,
        expected_query_results=(("SELECT val FROM main.layer_3", ((201,),)),),
    ),
]

FAILURE_TEST_CASES: list[ConcurrentBuildTestCase] = [
    ConcurrentBuildTestCase(
        description=(
            "failure in one independent branch does not affect the other with concurrency 2"
        ),
        max_concurrency=2,
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "models/broken.sql": ("MODEL (materialized table);\n\nSELECT * FROM nonexistent_table"),
            "models/healthy.sql": ("MODEL (materialized table);\n\nSELECT 42 AS val"),
        },
        expected_status=BuildStatus.FAILED,
        expected_success_count=1,
        expected_failure_count=1,
        expected_model_statuses=(
            ("broken", ExecutionStatus.FAILED),
            ("healthy", ExecutionStatus.SUCCESS),
        ),
        expected_query_results=(("SELECT val FROM main.healthy", ((42,),)),),
        expected_missing_relations=("main.broken",),
    ),
    ConcurrentBuildTestCase(
        description=(
            "failure blocks downstream but independent branch still completes with concurrency 2"
        ),
        max_concurrency=2,
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "models/broken.sql": ("MODEL (materialized table);\n\nSELECT * FROM nonexistent_table"),
            "models/downstream.sql": (
                'MODEL (materialized table);\n\nSELECT 1 AS id FROM __ref("broken")'
            ),
            "models/independent.sql": ("MODEL (materialized table);\n\nSELECT 99 AS val"),
        },
        expected_status=BuildStatus.FAILED,
        expected_success_count=1,
        expected_failure_count=1,
        expected_skipped_count=1,
        expected_model_statuses=(
            ("broken", ExecutionStatus.FAILED),
            ("downstream", ExecutionStatus.SKIPPED),
            ("independent", ExecutionStatus.SUCCESS),
        ),
        expected_query_results=(("SELECT val FROM main.independent", ((99,),)),),
        expected_missing_relations=(
            "main.broken",
            "main.downstream",
        ),
    ),
    ConcurrentBuildTestCase(
        description=("fail_fast stops dispatching independent nodes after first failure"),
        max_concurrency=1,
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "models/aaa_broken.sql": (
                "MODEL (materialized table);\n\nSELECT * FROM nonexistent_table"
            ),
            "models/zzz_independent.sql": ("MODEL (materialized table);\n\nSELECT 1 AS id"),
        },
        fail_fast=True,
        expected_status=BuildStatus.FAILED,
        expected_failure_count=1,
        expected_skipped_count=1,
        expected_model_statuses=(
            ("aaa_broken", ExecutionStatus.FAILED),
            ("zzz_independent", ExecutionStatus.SKIPPED),
        ),
        expected_missing_relations=(
            "main.aaa_broken",
            "main.zzz_independent",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SUCCESS_TEST_CASES,
    ids=[case.description for case in SUCCESS_TEST_CASES],
)
def test_given_concurrent_build_when_executing_then_succeeds(
    test_case: ConcurrentBuildTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    db_path: Path = tmp_path / "test.duckdb"

    result: BuildExecutionResult = run_concurrent_build(
        test_case=test_case,
        project_dir=tmp_path,
        db_path=db_path,
        adapter=adapter,
    )

    assert result.status == test_case.expected_status
    assert result.success_count == test_case.expected_success_count
    verify_concurrent_warehouse_state(db_path=db_path, adapter=adapter, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    FAILURE_TEST_CASES,
    ids=[case.description for case in FAILURE_TEST_CASES],
)
def test_given_concurrent_build_when_executing_then_fails(
    test_case: ConcurrentBuildTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    db_path: Path = tmp_path / "test.duckdb"

    result: BuildExecutionResult = run_concurrent_build(
        test_case=test_case,
        project_dir=tmp_path,
        db_path=db_path,
        adapter=adapter,
    )

    assert result.status == test_case.expected_status
    assert result.success_count == test_case.expected_success_count
    assert result.failure_count == test_case.expected_failure_count
    assert result.skipped_count == test_case.expected_skipped_count

    actual_statuses: dict[str, ExecutionStatus] = {
        r.model_name: r.status for r in result.model_results
    }
    expected_name: str
    expected_status: ExecutionStatus
    for expected_name, expected_status in test_case.expected_model_statuses:
        assert actual_statuses.get(expected_name) == expected_status, (
            f"{expected_name}: expected {expected_status}, got {actual_statuses.get(expected_name)}"
        )

    verify_concurrent_warehouse_state(db_path=db_path, adapter=adapter, test_case=test_case)
