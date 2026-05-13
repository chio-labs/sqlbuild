from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtExecutionCliTestCase,
    DbtExecutionFailureCliTestCase,
    DbtExecutionQueryAssertion,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    load_json_stdout,
    prepare_dbt_interop_project,
    skip_unless_dbt_is_runnable,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    query_duckdb,
    row_count,
    run_sqb,
    table_exists,
)

pytestmark: pytest.MarkDecorator = pytest.mark.dbt

EXECUTION_TEST_CASES: list[DbtExecutionCliTestCase] = [
    DbtExecutionCliTestCase(
        description="run executes mixed dbt and sqlbuild work",
        command=("dbt", "run", "--select", "+fact_orders+"),
        expected_row_counts=(
            ("stg_orders", 1),
            ("fact_orders", 1),
            ("downstream_orders", 1),
            ("event_time_orders", 1),
            ("mart_orders", 1),
        ),
        expected_stdout_fragments=(
            "Plan ready",
            "Running dbt:",
            "SQLBuild execution",
            "Completed successfully.",
        ),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="mixed run materializes downstream orders row",
                sql="SELECT order_id FROM main.downstream_orders ORDER BY order_id",
                expected_rows=((1,),),
            ),
            DbtExecutionQueryAssertion(
                description="mixed run materializes mart orders row",
                sql="SELECT order_id FROM main.mart_orders ORDER BY order_id",
                expected_rows=((1,),),
            ),
        ),
    ),
    DbtExecutionCliTestCase(
        description="run executes dbt only work",
        command=("dbt", "run", "--select", "dbt_only"),
        expected_row_counts=(("dbt_only", 1),),
        unexpected_relations=("local_only",),
    ),
    DbtExecutionCliTestCase(
        description="run executes sqlbuild only work",
        command=("dbt", "run", "--select", "local_only"),
        expected_row_counts=(("local_only", 1),),
        unexpected_relations=("dbt_only",),
        expected_stdout_fragments=("Skipping dbt: no dbt work selected.",),
        expected_absent_stdout_fragments=("test_local_only",),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="sqlbuild only run materializes local row",
                sql="SELECT order_id FROM main.local_only",
                expected_rows=((10,),),
            ),
        ),
    ),
    DbtExecutionCliTestCase(
        description="build executes mixed dbt and sqlbuild work",
        command=("dbt", "build", "--select", "+fact_orders+"),
        expected_row_counts=(
            ("stg_orders", 1),
            ("fact_orders", 1),
            ("downstream_orders", 1),
            ("event_time_orders", 1),
            ("mart_orders", 1),
        ),
        expected_stdout_fragments=(
            "Plan ready",
            "Running dbt:",
            "SQLBuild execution",
            "Completed successfully.",
        ),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="mixed build materializes downstream orders row",
                sql="SELECT order_id FROM main.downstream_orders ORDER BY order_id",
                expected_rows=((1,),),
            ),
            DbtExecutionQueryAssertion(
                description="mixed build materializes mart orders row",
                sql="SELECT order_id FROM main.mart_orders ORDER BY order_id",
                expected_rows=((1,),),
            ),
        ),
        expected_planned_sqlbuild_models=(
            "downstream_orders",
            "event_time_orders",
            "mart_orders",
        ),
    ),
    DbtExecutionCliTestCase(
        description="build executes direct mixed tag selector with required dbt upstream",
        command=("dbt", "build", "--select", "tag:nightly"),
        expected_row_counts=(
            ("stg_orders", 1),
            ("fact_orders", 1),
            ("downstream_orders", 1),
        ),
        unexpected_relations=("mart_orders",),
        expected_stdout_fragments=(
            "selectors: +fact_orders",
            "Running dbt:",
            "SQLBuild execution",
            "Completed successfully.",
        ),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="direct mixed tag materializes fact orders upstream row",
                sql="SELECT order_id FROM main.fact_orders",
                expected_rows=((1,),),
            ),
            DbtExecutionQueryAssertion(
                description="direct mixed tag materializes downstream row",
                sql="SELECT order_id FROM main.downstream_orders",
                expected_rows=((1,),),
            ),
        ),
        expected_planned_sqlbuild_models=("downstream_orders",),
    ),
    DbtExecutionCliTestCase(
        description="build executes dbt only work",
        command=("dbt", "build", "--select", "dbt_only"),
        expected_row_counts=(("dbt_only", 1),),
        unexpected_relations=("local_only",),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="dbt only build materializes dbt row",
                sql="SELECT order_id FROM main.dbt_only",
                expected_rows=((2,),),
            ),
        ),
    ),
    DbtExecutionCliTestCase(
        description="build executes sqlbuild only work",
        command=("dbt", "build", "--select", "local_only"),
        expected_row_counts=(("local_only", 1),),
        unexpected_relations=("dbt_only",),
        expected_stdout_fragments=("Skipping dbt: no dbt work selected.", "test_local_only"),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="sqlbuild only build materializes local row",
                sql="SELECT order_id FROM main.local_only",
                expected_rows=((10,),),
            ),
        ),
        rerun_count=2,
    ),
    DbtExecutionCliTestCase(
        description="run executes event time incremental sqlbuild work",
        command=(
            "dbt",
            "run",
            "--select",
            "event_time_orders",
            "--event-time-start",
            "2025-12-31",
            "--event-time-end",
            "2026-01-02",
        ),
        expected_row_counts=(
            ("stg_orders", 1),
            ("fact_orders", 1),
            ("event_time_orders", 1),
        ),
        expected_stdout_fragments=(
            "event_time_orders",
            "--event-time-start 2025-12-31",
            "--event-time-end 2026-01-02",
            "SQLBuild execution",
            "Completed successfully.",
        ),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="event time row preserves timestamp value",
                sql="SELECT order_id, CAST(ordered_at AS VARCHAR) FROM main.event_time_orders",
                expected_rows=((1, "2026-01-01 00:00:00"),),
            ),
        ),
        expected_planned_sqlbuild_models=("event_time_orders",),
    ),
    DbtExecutionCliTestCase(
        description="run executes full refresh sqlbuild work",
        command=("dbt", "run", "--full-refresh", "--select", "event_time_orders"),
        expected_row_counts=(
            ("stg_orders", 1),
            ("fact_orders", 1),
            ("event_time_orders", 1),
        ),
        expected_stdout_fragments=(
            "--full-refresh",
            "event_time_orders",
            "SQLBuild execution",
            "Completed successfully.",
        ),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="full refresh materializes event time row",
                sql="SELECT order_id, CAST(ordered_at AS VARCHAR) FROM main.event_time_orders",
                expected_rows=((1, "2026-01-01 00:00:00"),),
            ),
        ),
    ),
    DbtExecutionCliTestCase(
        description="run executes direct sqlbuild model with package qualified dbt ref",
        command=("dbt", "run", "--select", "downstream_orders"),
        expected_row_counts=(
            ("fact_orders", 1),
            ("downstream_orders", 1),
        ),
        unexpected_relations=("mart_orders",),
        expected_stdout_fragments=(
            "selectors: +fact_orders",
            "Running dbt:",
            "SQLBuild execution",
            "Completed successfully.",
        ),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="package qualified dbt ref materializes downstream row",
                sql="SELECT order_id FROM main.downstream_orders",
                expected_rows=((1,),),
            ),
        ),
        expected_planned_sqlbuild_models=("downstream_orders",),
    ),
    DbtExecutionCliTestCase(
        description="build executes path translation scope",
        command=(
            "dbt",
            "build",
            "--select",
            "path:models/marts",
            "--exclude",
            "deprecated_orders",
            "mart_orders",
            "event_time_orders",
        ),
        expected_row_counts=(
            ("fact_orders", 1),
            ("downstream_orders", 1),
        ),
        unexpected_relations=("deprecated_orders", "mart_orders", "event_time_orders"),
        expected_stdout_fragments=(
            "path:models/marts",
            "downstream_orders",
            "Completed successfully.",
        ),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="path translation materializes downstream row",
                sql="SELECT order_id FROM main.downstream_orders",
                expected_rows=((1,),),
            ),
        ),
        expected_planned_sqlbuild_models=("downstream_orders",),
    ),
    DbtExecutionCliTestCase(
        description="build executes exclude scope correctly",
        command=("dbt", "build", "--select", "tag:sqb_only", "--exclude", "tag:deprecated"),
        expected_row_counts=(("local_only", 1),),
        unexpected_relations=("deprecated_orders",),
        expected_stdout_fragments=("local_only", "Completed successfully."),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="exclude leaves local only row",
                sql="SELECT order_id FROM main.local_only",
                expected_rows=((10,),),
            ),
        ),
        expected_planned_sqlbuild_models=("local_only",),
    ),
]

EXECUTION_FAILURE_TEST_CASES: list[DbtExecutionFailureCliTestCase] = [
    DbtExecutionFailureCliTestCase(
        description="run stops before sqlbuild when dbt fails",
        command=("dbt", "run", "--select", "fact_orders+"),
        expected_stdout_fragments=("Running dbt:", "Completed with 1 error"),
        expected_absent_stdout_fragments=("SQLBuild execution",),
        expected_absent_relations=("downstream_orders", "mart_orders"),
    ),
    DbtExecutionFailureCliTestCase(
        description="build stops before sqlbuild when dbt fails",
        command=("dbt", "build", "--select", "fact_orders+"),
        expected_stdout_fragments=("Running dbt:", "Completed with 1 error"),
        expected_absent_stdout_fragments=("SQLBuild execution",),
        expected_absent_relations=("downstream_orders", "mart_orders"),
    ),
]

PLAN_CONSISTENCY_TEST_CASES: list[DbtExecutionCliTestCase] = [
    DbtExecutionCliTestCase(
        description="plan consistency for mixed build case",
        command=("dbt", "build", "--select", "+fact_orders+"),
        expected_row_counts=(),
        expected_planned_sqlbuild_models=(
            "downstream_orders",
            "event_time_orders",
            "mart_orders",
        ),
    ),
    DbtExecutionCliTestCase(
        description="plan consistency for direct mixed tag case",
        command=("dbt", "build", "--select", "tag:nightly"),
        expected_row_counts=(),
        expected_planned_sqlbuild_models=("downstream_orders",),
    ),
    DbtExecutionCliTestCase(
        description="plan consistency for event time case",
        command=(
            "dbt",
            "run",
            "--select",
            "event_time_orders",
            "--event-time-start",
            "2025-12-31",
            "--event-time-end",
            "2026-01-02",
        ),
        expected_row_counts=(),
        expected_planned_sqlbuild_models=("event_time_orders",),
    ),
    DbtExecutionCliTestCase(
        description="plan consistency for package qualified ref case",
        command=("dbt", "run", "--select", "downstream_orders"),
        expected_row_counts=(),
        expected_planned_sqlbuild_models=("downstream_orders",),
    ),
    DbtExecutionCliTestCase(
        description="plan consistency for path translation case",
        command=(
            "dbt",
            "build",
            "--select",
            "path:models/marts",
            "--exclude",
            "deprecated_orders",
            "mart_orders",
            "event_time_orders",
        ),
        expected_row_counts=(),
        expected_planned_sqlbuild_models=("downstream_orders",),
    ),
    DbtExecutionCliTestCase(
        description="plan consistency for exclude case",
        command=("dbt", "build", "--select", "tag:sqb_only", "--exclude", "tag:deprecated"),
        expected_row_counts=(),
        expected_planned_sqlbuild_models=("local_only",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    EXECUTION_TEST_CASES,
    ids=[case.description for case in EXECUTION_TEST_CASES],
)
def test_given_dbt_interop_project_when_running_execution_command_then_outputs_expected_relations(
    test_case: DbtExecutionCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    db_path: Path = project_dir / "dbt_interop.duckdb"
    assert result.returncode == 0, result.stderr or result.stdout
    for _ in range(test_case.rerun_count - 1):
        result = run_sqb(command=test_case.command, project_dir=project_dir)
        assert result.returncode == 0, result.stderr or result.stdout
    relation_name: str
    expected_row_count: int
    for relation_name, expected_row_count in test_case.expected_row_counts:
        assert table_exists(db_path=db_path, table_name=relation_name), relation_name
        assert row_count(db_path=db_path, table_name=relation_name) == expected_row_count
    for relation_name in test_case.unexpected_relations:
        assert not table_exists(db_path=db_path, table_name=relation_name), relation_name
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    absent_fragment: str
    for absent_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_fragment not in result.stdout
    query_assertion: DbtExecutionQueryAssertion
    for query_assertion in test_case.expected_query_assertions:
        assert query_duckdb(db_path=db_path, sql=query_assertion.sql) == list(
            query_assertion.expected_rows
        ), query_assertion.description


@pytest.mark.parametrize(
    "test_case",
    PLAN_CONSISTENCY_TEST_CASES,
    ids=[case.description for case in PLAN_CONSISTENCY_TEST_CASES],
)
def test_given_dbt_interop_execution_case_when_planning_then_selected_models_match_expectation(
    test_case: DbtExecutionCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)

    planned_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--json", *test_case.command[2:]),
        project_dir=project_dir,
    )

    assert planned_result.returncode == 0, planned_result.stderr or planned_result.stdout
    planned_payload: dict[str, object] = load_json_stdout(planned_result.stdout)
    planned_sqlbuild_payload: object = planned_payload["sqlbuild"]
    assert isinstance(planned_sqlbuild_payload, dict)
    typed_sqlbuild_payload: Mapping[str, object] = cast(
        Mapping[str, object], planned_sqlbuild_payload
    )
    assert typed_sqlbuild_payload["selected_models"] == list(
        test_case.expected_planned_sqlbuild_models or ()
    )


@pytest.mark.parametrize(
    "test_case",
    EXECUTION_FAILURE_TEST_CASES,
    ids=[case.description for case in EXECUTION_FAILURE_TEST_CASES],
)
def test_given_failing_dbt_execution_when_running_command_then_sqlbuild_does_not_run(
    test_case: DbtExecutionFailureCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 1
    db_path: Path = project_dir / "dbt_interop.duckdb"
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    absent_fragment: str
    for absent_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_fragment not in result.stdout
    relation_name: str
    for relation_name in test_case.expected_absent_relations:
        assert not table_exists(db_path=db_path, table_name=relation_name), relation_name
