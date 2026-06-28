from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtCloneE2ETestCase,
    DbtExecutionCliTestCase,
    DbtExecutionFailureCliTestCase,
    DbtExecutionQueryAssertion,
    DbtExistingRelationGuardE2ETestCase,
    DbtMissingRelationGuardE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    break_dbt_interop_fact_orders_model,
    load_json_stdout,
    prepare_dbt_diff_workspace,
    prepare_dbt_interop_project,
    skip_unless_dbt_is_runnable,
    write_dbt_diff_orders_model,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    execute_duckdb,
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
            "dbt execution",
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
            "dbt execution",
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
            "+event_time_orders",
            "mart_orders",
        ),
    ),
    DbtExecutionCliTestCase(
        description="build executes explicit upstream mixed tag selector",
        command=("dbt", "build", "--select", "+tag:nightly"),
        expected_row_counts=(
            ("stg_orders", 1),
            ("fact_orders", 1),
            ("downstream_orders", 1),
        ),
        unexpected_relations=("mart_orders",),
        expected_stdout_fragments=(
            "dbt execution",
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
        expected_planned_sqlbuild_models=("downstream_orders", "local_only"),
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
        expected_stdout_fragments=("Skipping dbt: no dbt work selected.",),
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
            "+event_time_orders",
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
        command=("dbt", "run", "--full-refresh", "--select", "+event_time_orders"),
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
        description="run executes explicit upstream sqlbuild model with package qualified dbt ref",
        command=("dbt", "run", "--select", "+downstream_orders"),
        expected_row_counts=(
            ("fact_orders", 1),
            ("downstream_orders", 1),
        ),
        unexpected_relations=("mart_orders",),
        expected_stdout_fragments=(
            "dbt execution",
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
        expected_planned_sqlbuild_models=("downstream_orders", "local_only"),
    ),
    DbtExecutionCliTestCase(
        description="build executes path translation scope",
        command=(
            "dbt",
            "build",
            "--select",
            "+path:models/marts",
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
            "downstream_orders",
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
        expected_planned_sqlbuild_models=("downstream_orders", "local_only"),
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
        description="run skips dependent sqlbuild work when dbt model fails",
        command=("dbt", "run", "--select", "fact_orders+"),
        expected_stdout_fragments=(
            "dbt execution",
            "fact_orders",
            "skip: external_upstream_failed",
        ),
        expected_absent_stdout_fragments=(),
        expected_returncode=1,
        expected_absent_relations=("downstream_orders", "mart_orders"),
        setup=break_dbt_interop_fact_orders_model,
    ),
    DbtExecutionFailureCliTestCase(
        description="build skips dependent sqlbuild work when dbt model fails",
        command=("dbt", "build", "--select", "fact_orders+"),
        expected_stdout_fragments=(
            "dbt execution",
            "fact_orders",
            "skip: external_upstream_failed",
        ),
        expected_absent_stdout_fragments=(),
        expected_returncode=1,
        expected_absent_relations=("downstream_orders", "mart_orders"),
        setup=break_dbt_interop_fact_orders_model,
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
        description="plan consistency for explicit upstream mixed tag case",
        command=("dbt", "build", "--select", "+tag:nightly"),
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
        description="plan consistency for explicit upstream package qualified ref case",
        command=("dbt", "run", "--select", "+downstream_orders"),
        expected_row_counts=(),
        expected_planned_sqlbuild_models=("downstream_orders",),
    ),
    DbtExecutionCliTestCase(
        description="plan consistency for path translation case",
        command=(
            "dbt",
            "build",
            "--select",
            "+path:models/marts",
            "--exclude",
            "deprecated_orders",
            "mart_orders",
            "event_time_orders",
        ),
        expected_row_counts=(),
        expected_planned_sqlbuild_models=("downstream_orders", "local_only"),
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
    [
        DbtMissingRelationGuardE2ETestCase(
            description="plain SQLBuild selection blocks when dbt upstream relation is missing",
            command=("dbt", "build", "--select", "downstream_orders"),
            expected_returncode=1,
            expected_stdout_fragments=(
                "Skipping dbt: no dbt work selected.",
                "depends on missing dbt relation(s):",
                "fact_orders",
                "Use --select +downstream_orders",
            ),
            expected_absent_relations=("fact_orders", "downstream_orders"),
        )
    ],
    ids=["plain SQLBuild selection blocks when dbt upstream relation is missing"],
)
def test_given_plain_sqlbuild_selection_with_missing_dbt_ref_when_running_then_blocks_before_build(
    tmp_path: Path,
    test_case: DbtMissingRelationGuardE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    db_path: Path = project_dir / "dbt_interop.duckdb"
    assert result.returncode == test_case.expected_returncode, result.stderr or result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    absent_relation: str
    for absent_relation in test_case.expected_absent_relations:
        assert not table_exists(db_path=db_path, table_name=absent_relation)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExistingRelationGuardE2ETestCase(
            description="plain SQLBuild selection builds when dbt upstream relation already exists",
            command=("dbt", "build", "--select", "downstream_orders"),
            setup_sql="CREATE TABLE main.fact_orders AS SELECT 1 AS order_id, 100 AS amount",
            expected_returncode=0,
            expected_stdout_fragments=("Skipping dbt: no dbt work selected.",),
            unexpected_stdout_fragments=("depends on missing dbt relation",),
            expected_rows=((1,),),
        )
    ],
    ids=["plain SQLBuild selection builds when dbt upstream relation already exists"],
)
def test_given_plain_sqlbuild_selection_with_existing_dbt_ref_when_running_then_builds_downstream(
    tmp_path: Path,
    test_case: DbtExistingRelationGuardE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_interop.duckdb"
    execute_duckdb(
        db_path=db_path,
        sql=test_case.setup_sql,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr or result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    unexpected_stdout_fragment: str
    for unexpected_stdout_fragment in test_case.unexpected_stdout_fragments:
        assert unexpected_stdout_fragment not in result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_rows)


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
def test_given_failing_dbt_model_when_running_command_then_dependent_sqlbuild_is_skipped(
    test_case: DbtExecutionFailureCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    test_case.setup(project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr or result.stdout
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCloneE2ETestCase(
            description="dbt build defer-clones dbt boundary before sqlbuild downstream build",
            command=(
                "--no-color",
                "dbt",
                "build",
                "--select",
                "downstream_orders",
                "--defer-clone-from",
            ),
            expected_returncode=0,
            expected_stdout_fragments=(
                "Compiling dbt production ref git ref 'prod'",
                "Cloning deferred dbt boundary relations",
                "Prephase  dbt defer clone",
                "[for downstream_orders]",
                "Skipping dbt: no dbt work selected.",
                "SQLBuild execution",
                "downstream_orders",
                "Completed successfully.",
            ),
            expected_rows=((1, 900), (2, 900)),
            rows_sql=(
                "SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id"
            ),
        )
    ],
    ids=["dbt build defer-clones dbt boundary before sqlbuild downstream build"],
)
def test_given_sqlbuild_downstream_when_dbt_building_with_defer_clone_then_clones_dbt_boundary(
    tmp_path: Path,
    test_case: DbtCloneE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name="dbt_defer_clone_workspace",
    )
    sqlbuild_model_dir: Path = workspace / "sqlbuild_project" / "models"
    sqlbuild_model_dir.mkdir(exist_ok=True)
    sqlbuild_model_dir.joinpath("downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        "SELECT order_id, amount_cents AS downstream_amount "
        'FROM __dbt_ref("analytics", "dbt_orders")\n',
        encoding="utf-8",
    )
    write_dbt_diff_orders_model(
        workspace=workspace,
        amount_cents=111,
        order_ids=(1, 3),
        include_unique_key=True,
        include_cursor_meta=True,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr
    assert (
        tuple(query_duckdb(db_path=workspace / "warehouse.duckdb", sql=test_case.rows_sql))
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCloneE2ETestCase(
            description="dbt build defer-clones dbt boundary for pure dbt selection",
            command=(
                "--no-color",
                "dbt",
                "build",
                "--select",
                "dbt_bias",
                "--defer-clone-from",
            ),
            expected_returncode=0,
            expected_stdout_fragments=(
                "Compiling dbt production ref git ref 'prod'",
                "Cloning deferred dbt boundary relations",
                "Prephase  dbt defer clone",
                "[for dbt_bias]",
                "Prephase  dbt defer clone views",
                "dbt_order_summary",
                "dbt execution",
                "dbt_bias",
                "SQLBuild (0 selected)",
                "skipped: no SQLBuild work selected",
                "Completed successfully.",
            ),
            expected_rows=((1, 900), (2, 900)),
            rows_sql="SELECT order_id, bias_amount_cents FROM main.dbt_bias ORDER BY order_id",
        )
    ],
    ids=["dbt build defer-clones dbt boundary for pure dbt selection"],
)
def test_given_pure_dbt_selection_when_building_with_defer_clone_then_clones_dbt_boundary(
    tmp_path: Path,
    test_case: DbtCloneE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name="dbt_pure_defer_clone_workspace",
        include_defer_clone_chain=True,
    )
    write_dbt_diff_orders_model(
        workspace=workspace,
        amount_cents=111,
        order_ids=(1, 3),
        include_unique_key=True,
        include_cursor_meta=True,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    assert (
        tuple(query_duckdb(db_path=workspace / "warehouse.duckdb", sql=test_case.rows_sql))
        == test_case.expected_rows
    )
