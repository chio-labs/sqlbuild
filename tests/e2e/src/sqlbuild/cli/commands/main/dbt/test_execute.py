from __future__ import annotations

import base64
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtDependencyBaselinePlanJsonE2ETestCase,
    DbtDependencyBaselineReuseFromE2ETestCase,
    DbtExecutionCliTestCase,
    DbtExecutionFailureCliTestCase,
    DbtExecutionQueryAssertion,
    DbtExistingRelationGuardE2ETestCase,
    DbtMissingRelationGuardE2ETestCase,
    DbtMultiNodeCompleteReuseFromE2ETestCase,
    DbtMultiNodeSeededReuseFromE2ETestCase,
    DbtReuseFromE2ETestCase,
    DbtSeededReuseFromE2ETestCase,
    DbtSnapshotSeededReuseFromE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    load_json_stdout,
    prepare_dbt_interop_project,
    prepare_dbt_multi_node_reuse_from_project,
    prepare_dbt_multi_node_seeded_reuse_from_project,
    prepare_dbt_reuse_from_project,
    prepare_dbt_seeded_reuse_from_project,
    prepare_dbt_snapshot_seeded_reuse_from_project,
    skip_unless_dbt_is_runnable,
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
    [
        DbtReuseFromE2ETestCase(
            description="explicit upstream selection reuses missing dbt upstream from prod ref",
            command=("dbt", "build", "--select", "+downstream_orders"),
            expected_destination_rows=((1, 900),),
            expected_downstream_rows=((1, 900),),
            expected_rerun_destination_rows=((1, 900),),
            expected_fingerprint_rows=(("dbt", "model.analytics.fact_orders"),),
            expected_metadata_json=(
                '{"dbt_target_name":"dev",'
                '"destination_relation":"\\"dbt_reuse_from\\".\\"main\\".\\"fact_orders\\"",'
                '"execution_mode":"reuse","materialization":"table",'
                '"origin_relation":"\\"dbt_reuse_from\\".\\"prod\\".\\"fact_orders\\"",'
                '"reuse_mode":"complete",'
                '"status":"success"}'
            ),
            expected_stdout_fragments=(
                "dbt reuse",
                "model.analytics.fact_orders",
                "OK     reuse",
            ),
            expected_absent_relations=(("main", "unrelated_model"),),
            expected_absent_stdout_fragments=(
                "depends on missing dbt relation",
                "dbt execution",
            ),
            expected_rerun_absent_stdout_fragments=(
                "dbt reuse  pre-phase",
                "dbt execution",
            ),
        )
    ],
    ids=["explicit upstream selection reuses missing dbt upstream from prod ref"],
)
def test_given_explicit_upstream_selection_with_reuse_from_when_ref_missing_then_reuses_prod_table(
    tmp_path: Path,
    test_case: DbtReuseFromE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_reuse_from_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_reuse_from.duckdb"
    assert table_exists(db_path=db_path, table_name="fact_orders", schema="prod")
    assert not table_exists(db_path=db_path, table_name="fact_orders", schema="main")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_stdout_fragment not in result.stdout
    assert table_exists(db_path=db_path, table_name="fact_orders", schema="prod")
    assert table_exists(db_path=db_path, table_name="fact_orders", schema="main")
    assert table_exists(db_path=db_path, table_name="downstream_orders", schema="main")
    absent_schema: str
    absent_relation: str
    for absent_schema, absent_relation in test_case.expected_absent_relations:
        assert not table_exists(db_path=db_path, table_name=absent_relation, schema=absent_schema)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_destination_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_downstream_rows)
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_type, node_name FROM main._sqlbuild_fingerprints "
            "WHERE node_type = 'dbt' AND node_name = 'model.analytics.fact_orders'"
        ),
    ) == list(test_case.expected_fingerprint_rows)
    metadata_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT metadata_json_b64 "
            "FROM main._sqlbuild_fingerprints "
            "WHERE node_type = 'dbt' AND node_name = 'model.analytics.fact_orders'"
        ),
    )
    assert base64.b64decode(str(metadata_rows[0][0])).decode("utf-8") == (
        test_case.expected_metadata_json
    )

    execute_duckdb(
        db_path=db_path,
        sql="UPDATE prod.fact_orders SET amount = 901 WHERE order_id = 1",
    )
    rerun_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert rerun_result.returncode == 0, rerun_result.stderr or rerun_result.stdout
    rerun_absent_stdout_fragment: str
    for rerun_absent_stdout_fragment in test_case.expected_rerun_absent_stdout_fragments:
        assert rerun_absent_stdout_fragment not in rerun_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_rerun_destination_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeededReuseFromE2ETestCase(
            description="seeded reuse pre-seeds incremental relation before dbt catch-up",
            command=("dbt", "build", "--select", "+downstream_orders"),
            expected_destination_rows=((1, 900), (2, 901)),
            expected_downstream_rows=((1, 900), (2, 901)),
            expected_stdout_fragments=(
                "dbt reuse",
                "model.analytics.fact_orders",
                "OK     baseline reuse before dbt catch-up",
                "dbt execution",
                "SQLBuild execution",
            ),
            expected_rerun_absent_stdout_fragments=("dbt reuse  pre-phase",),
        )
    ],
    ids=["seeded reuse pre-seeds incremental relation before dbt catch-up"],
)
def test_given_seeded_reuse_from_when_incremental_model_runs_then_dbt_catches_up(
    tmp_path: Path,
    test_case: DbtSeededReuseFromE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seeded_reuse_from_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_seeded_reuse_from.duckdb"
    assert table_exists(db_path=db_path, table_name="fact_orders", schema="prod")
    assert not table_exists(db_path=db_path, table_name="fact_orders", schema="main")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_destination_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_downstream_rows)

    rerun_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert rerun_result.returncode == 0, rerun_result.stderr or rerun_result.stdout
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_rerun_absent_stdout_fragments:
        assert absent_stdout_fragment not in rerun_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_destination_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtMultiNodeCompleteReuseFromE2ETestCase(
            description="multi-node complete reuse resumes after later origin failure",
            command=("dbt", "build", "--select", "+downstream_orders"),
            failure_sql="DROP TABLE prod.orders_c",
            recovery_sql=(
                "CREATE TABLE prod.orders_c AS SELECT 'orders_c' AS model_name, 900 AS amount"
            ),
            expected_failed_destination_rows=(("orders_a", 900), ("orders_b", 900)),
            expected_failed_fingerprint_rows=(
                ("model.analytics.orders_a",),
                ("model.analytics.orders_b",),
            ),
            expected_rerun_downstream_rows=(
                ("orders_a", 900),
                ("orders_b", 900),
                ("orders_c", 900),
            ),
            expected_rerun_fingerprint_rows=(
                ("model.analytics.orders_a",),
                ("model.analytics.orders_b",),
                ("model.analytics.orders_c",),
            ),
            expected_absent_failed_relation=("main", "orders_c"),
            expected_failed_absent_stdout_fragments=("dbt reuse  pre-phase",),
            expected_rerun_stdout_fragments=(
                "dbt reuse",
                "model.analytics.orders_c",
                "OK     reuse",
            ),
            expected_rerun_absent_stdout_fragments=(
                "model.analytics.orders_a        OK",
                "model.analytics.orders_b        OK",
            ),
        )
    ],
    ids=["multi-node complete reuse resumes after later origin failure"],
)
def test_given_multi_node_complete_reuse_when_later_origin_missing_then_rerun_resumes_failed_node(
    tmp_path: Path,
    test_case: DbtMultiNodeCompleteReuseFromE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_multi_node_reuse_from_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_multi_node_reuse_from.duckdb"
    execute_duckdb(db_path=db_path, sql=test_case.failure_sql)

    failed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert failed_result.returncode != 0
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_failed_absent_stdout_fragments:
        assert absent_stdout_fragment not in failed_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT model_name, amount FROM main.orders_a "
            "UNION ALL "
            "SELECT model_name, amount FROM main.orders_b "
            "ORDER BY model_name"
        ),
    ) == list(test_case.expected_failed_destination_rows)
    absent_schema, absent_relation = test_case.expected_absent_failed_relation
    assert not table_exists(db_path=db_path, table_name=absent_relation, schema=absent_schema)
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_name FROM main._sqlbuild_fingerprints "
            "WHERE node_type = 'dbt' ORDER BY node_name"
        ),
    ) == list(test_case.expected_failed_fingerprint_rows)

    execute_duckdb(db_path=db_path, sql=test_case.recovery_sql)
    rerun_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert rerun_result.returncode == 0, rerun_result.stderr or rerun_result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_rerun_stdout_fragments:
        assert expected_stdout_fragment in rerun_result.stdout
    absent_stdout_fragment = ""
    for absent_stdout_fragment in test_case.expected_rerun_absent_stdout_fragments:
        assert absent_stdout_fragment not in rerun_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT model_name, downstream_amount FROM main.downstream_orders ORDER BY model_name"
        ),
    ) == list(test_case.expected_rerun_downstream_rows)
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_name FROM main._sqlbuild_fingerprints "
            "WHERE node_type = 'dbt' ORDER BY node_name"
        ),
    ) == list(test_case.expected_rerun_fingerprint_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtMultiNodeSeededReuseFromE2ETestCase(
            description=(
                "multi-node seeded reuse resumes from live cursors after later origin failure"
            ),
            command=("dbt", "build", "--select", "+downstream_orders"),
            failure_sql="DROP TABLE prod.orders_c",
            recovery_sql=(
                "CREATE TABLE prod.orders_c AS "
                "SELECT 'orders_c' AS model_name, 1 AS order_id, 900 AS amount, "
                "TIMESTAMP '2026-01-01' AS event_time"
            ),
            expected_failed_destination_rows=(("orders_a", 1, 900), ("orders_b", 1, 900)),
            expected_absent_failed_relation=("main", "orders_c"),
            expected_failed_absent_stdout_fragments=("dbt reuse  pre-phase",),
            expected_rerun_stdout_fragments=(
                "dbt reuse",
                "model.analytics.orders_c",
                "OK     baseline reuse before dbt catch-up",
            ),
            expected_rerun_absent_stdout_fragments=(
                "model.analytics.orders_a        OK",
                "model.analytics.orders_b        OK",
            ),
            expected_rerun_downstream_rows=(
                ("orders_a", 1, 900),
                ("orders_a", 2, 901),
                ("orders_b", 1, 900),
                ("orders_b", 2, 901),
                ("orders_c", 1, 900),
                ("orders_c", 2, 901),
            ),
        )
    ],
    ids=["multi-node seeded reuse resumes from live cursors after later origin failure"],
)
def test_given_multi_node_seeded_reuse_when_later_origin_missing_then_rerun_uses_live_cursors(
    tmp_path: Path,
    test_case: DbtMultiNodeSeededReuseFromE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_multi_node_seeded_reuse_from_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_multi_node_seeded_reuse_from.duckdb"
    execute_duckdb(db_path=db_path, sql=test_case.failure_sql)

    failed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert failed_result.returncode != 0
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_failed_absent_stdout_fragments:
        assert absent_stdout_fragment not in failed_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT model_name, order_id, amount FROM main.orders_a "
            "UNION ALL "
            "SELECT model_name, order_id, amount FROM main.orders_b "
            "ORDER BY model_name, order_id"
        ),
    ) == list(test_case.expected_failed_destination_rows)
    absent_schema, absent_relation = test_case.expected_absent_failed_relation
    assert not table_exists(db_path=db_path, table_name=absent_relation, schema=absent_schema)

    execute_duckdb(db_path=db_path, sql=test_case.recovery_sql)
    rerun_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert rerun_result.returncode == 0, rerun_result.stderr or rerun_result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_rerun_stdout_fragments:
        assert expected_stdout_fragment in rerun_result.stdout
    absent_stdout_fragment = ""
    for absent_stdout_fragment in test_case.expected_rerun_absent_stdout_fragments:
        assert absent_stdout_fragment not in rerun_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT model_name, order_id, downstream_amount FROM main.downstream_orders "
            "ORDER BY model_name, order_id"
        ),
    ) == list(test_case.expected_rerun_downstream_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSnapshotSeededReuseFromE2ETestCase(
            description="snapshot seeded reuse pre-seeds snapshot before dbt catch-up",
            command=("dbt", "build", "--select", "+downstream_orders"),
            expected_destination_rows=((1, 900), (2, 901)),
            expected_downstream_rows=((1, 900), (2, 901)),
            expected_stdout_fragments=(
                "dbt reuse",
                "snapshot.analytics.orders_snapshot",
                "OK     baseline reuse before dbt catch-up",
                "dbt execution",
                "SQLBuild execution",
            ),
            expected_rerun_absent_stdout_fragments=("dbt reuse  pre-phase",),
        )
    ],
    ids=["snapshot seeded reuse pre-seeds snapshot before dbt catch-up"],
)
def test_given_snapshot_seeded_reuse_from_when_snapshot_runs_then_dbt_catches_up(
    tmp_path: Path,
    test_case: DbtSnapshotSeededReuseFromE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_snapshot_seeded_reuse_from_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_snapshot_seeded_reuse_from.duckdb"
    assert table_exists(db_path=db_path, table_name="orders_snapshot", schema="prod")
    assert not table_exists(db_path=db_path, table_name="orders_snapshot", schema="main")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT order_id, amount FROM main.orders_snapshot "
            "WHERE dbt_valid_to IS NULL ORDER BY order_id"
        ),
    ) == list(test_case.expected_destination_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_downstream_rows)

    rerun_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert rerun_result.returncode == 0, rerun_result.stderr or rerun_result.stdout
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_rerun_absent_stdout_fragments:
        assert absent_stdout_fragment not in rerun_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtDependencyBaselineReuseFromE2ETestCase(
            description=("plain sqlbuild selection baselines dbt dependency without dbt catch-up"),
            command=("dbt", "build", "--select", "downstream_orders"),
            expected_destination_rows=((1, 900),),
            expected_downstream_rows=((1, 900),),
            expected_dbt_fingerprint_rows=(),
            expected_stdout_fragments=(
                "dbt (0 selected resources)",
                "Dependency baseline",
                "model.analytics.fact_orders",
                "baseline reuse",
                "Skipping dbt: no dbt work selected.",
                "SQLBuild execution",
            ),
            expected_absent_stdout_fragments=(
                "depends on missing dbt relation",
                "dbt execution",
                "baseline reuse before dbt catch-up",
            ),
        )
    ],
    ids=["plain sqlbuild selection baselines dbt dependency without dbt catch-up"],
)
def test_given_plain_selection_with_reuse_from_when_dbt_ref_missing_then_baselines_dependency(
    tmp_path: Path,
    test_case: DbtDependencyBaselineReuseFromE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seeded_reuse_from_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_seeded_reuse_from.duckdb"
    assert table_exists(db_path=db_path, table_name="fact_orders", schema="prod")
    assert not table_exists(db_path=db_path, table_name="fact_orders", schema="main")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_stdout_fragment not in result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_destination_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_downstream_rows)
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_type, node_name FROM main._sqlbuild_fingerprints "
            "WHERE node_type = 'dbt' ORDER BY node_name"
        ),
    ) == list(test_case.expected_dbt_fingerprint_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtDependencyBaselinePlanJsonE2ETestCase(
            description="plain sqlbuild selection exposes dbt dependency baseline in JSON",
            command=("dbt", "plan", "--json", "--select", "downstream_orders"),
            expected_selected_models=("downstream_orders",),
            expected_seeded_reuse_unique_ids=("model.analytics.fact_orders",),
            expected_entry_action="seeded_reuse",
            expected_entry_reason="fingerprint_missing",
            expected_entry_materialization="incremental",
        )
    ],
    ids=["plain sqlbuild selection exposes dbt dependency baseline in JSON"],
)
def test_given_plain_selection_with_reuse_from_when_planning_json_then_shows_dependency_baseline(
    tmp_path: Path,
    test_case: DbtDependencyBaselinePlanJsonE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seeded_reuse_from_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload: dict[str, object] = load_json_stdout(result.stdout)
    sqlbuild_payload: object = payload["sqlbuild"]
    assert isinstance(sqlbuild_payload, dict)
    typed_sqlbuild_payload: Mapping[str, object] = cast(Mapping[str, object], sqlbuild_payload)
    assert typed_sqlbuild_payload["selected_models"] == list(test_case.expected_selected_models)
    dbt_payload: object = payload["dbt"]
    assert isinstance(dbt_payload, dict)
    typed_dbt_payload: Mapping[str, object] = cast(Mapping[str, object], dbt_payload)
    baseline_payload: object = typed_dbt_payload["dependency_baseline_plan"]
    assert isinstance(baseline_payload, dict)
    typed_baseline_payload: Mapping[str, object] = cast(Mapping[str, object], baseline_payload)
    assert typed_baseline_payload["seeded_reuse_unique_ids"] == list(
        test_case.expected_seeded_reuse_unique_ids
    )
    entries_payload: object = typed_baseline_payload["entries"]
    assert isinstance(entries_payload, list)
    assert len(entries_payload) == 1
    entry_payload: object = entries_payload[0]
    assert isinstance(entry_payload, dict)
    typed_entry_payload: Mapping[str, object] = cast(Mapping[str, object], entry_payload)
    assert typed_entry_payload["action"] == test_case.expected_entry_action
    assert typed_entry_payload["reason"] == test_case.expected_entry_reason
    assert typed_entry_payload["materialization"] == test_case.expected_entry_materialization


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
