from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualExplicitCheckpointRollbackE2ETestCase,
    VirtualPartialRollbackE2ETestCase,
    VirtualRollbackE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    build_virtual_multi_seed_lifecycle_repo_files,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_repo_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="rollback blocks when checkpoint physical relation is missing",
            rollback_command=("--no-color", "rollback"),
            expected_exit_code=1,
            expected_rollback_fragments=(),
            expected_stderr_fragments=(
                "error[S024]",
                "checkpoint references missing warehouse relation",
            ),
            expected_query_results=(),
            expected_checkpoint_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_checkpoint_physical_relation_missing_when_rolling_back_then_it_blocks_cleanly(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_missing_physical",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, initial_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count
    initial_physical_relation: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT pr.schema_name, pr.relation_name "
            "FROM sqlbuild_state.virtual_environment_checkpoints cp "
            "JOIN sqlbuild_state.virtual_environment_checkpoint_model_refs cr "
            "ON cp.checkpoint_id = cr.checkpoint_id "
            "JOIN sqlbuild_state.physical_relations pr "
            "ON pr.artifact_type = 'model' AND pr.artifact_name = cr.model_name "
            "AND pr.version_hash = cr.version_hash "
            "WHERE cp.virtual_environment_name = 'dev' AND cr.model_name = 'stg_orders' "
            "ORDER BY cp.created_at ASC LIMIT 1"
        ),
    )
    assert initial_physical_relation
    schema_name, relation_name = initial_physical_relation[0]
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=f'DROP TABLE "{schema_name}"."{relation_name}"',
    )

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in rollback_result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="rollback blocks when no previous checkpoint exists",
            rollback_command=("--no-color", "rollback"),
            expected_exit_code=1,
            expected_rollback_fragments=(),
            expected_stderr_fragments=(
                "error[S021]",
                "no previous finalized checkpoint is available for rollback",
            ),
            expected_query_results=(),
            expected_checkpoint_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_only_current_checkpoint_when_rolling_back_then_it_blocks_cleanly(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_no_previous",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in rollback_result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="rollback blocks when target VDE lock exists",
            rollback_command=("rollback", "--virtual-env", "dev"),
            expected_exit_code=1,
            expected_rollback_fragments=(),
            expected_stderr_fragments=("virtual environment 'dev' is locked",),
            expected_query_results=(),
            expected_checkpoint_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_virtual_environment_lock_when_rolling_back_then_it_fails_clearly(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_locked_target",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, initial_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) "
            "VALUES ('virtual_env:dev', 'test-owner', TIMESTAMP '2999-01-01', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in rollback_result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="checkpoint show blocks for unknown checkpoint",
            rollback_command=("--no-color", "state", "checkpoints", "show", "missing"),
            expected_exit_code=1,
            expected_rollback_fragments=(),
            expected_stderr_fragments=("error[C905]", "unknown checkpoint 'missing'"),
            expected_query_results=(),
            expected_checkpoint_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_checkpoint_when_showing_checkpoint_then_it_blocks_cleanly(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_checkpoint_show_unknown",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="whole VDE rollback restores previous finalized checkpoint",
            rollback_command=("--no-color", "rollback"),
            expected_rollback_fragments=(
                "\u2713 Virtual rollback complete",
                "virtual environment  dev",
                "status               finalized",
                "rolled back models   2",
                "rolled back model set",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
            expected_checkpoint_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_finalized_checkpoints_when_rolling_back_then_it_restores_previous_refs_and_views(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_whole",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, initial_build_result.stderr
    initial_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
            "ORDER BY node_name"
        ),
    )
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count
    checkpoint_id: str = str(checkpoint_rows[0][0])
    list_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "list"),
        project_dir=project_dir,
    )
    assert list_result.returncode == 0, list_result.stderr
    assert "Virtual environment checkpoints" in list_result.stdout
    assert "dev" in list_result.stdout
    assert checkpoint_id in list_result.stdout
    show_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "show", checkpoint_id),
        project_dir=project_dir,
    )
    assert show_result.returncode == 0, show_result.stderr
    assert "Virtual environment checkpoint" in show_result.stdout
    assert checkpoint_id in show_result.stdout
    assert "stg_orders" in show_result.stdout
    diff_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "diff", checkpoint_id),
        project_dir=project_dir,
    )
    assert diff_result.returncode == 0, diff_result.stderr
    assert "Virtual environment checkpoint diff" in diff_result.stdout
    assert "changed refs     2" in diff_result.stdout
    assert "stg_orders" in diff_result.stdout

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    fragment: str
    for fragment in test_case.expected_rollback_fragments:
        assert fragment in rollback_result.stdout
    rolled_back_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
            "ORDER BY node_name"
        ),
    )
    assert rolled_back_ref_rows == initial_ref_rows
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="whole rollback restores seed refs and views",
            rollback_command=("--no-color", "rollback"),
            expected_rollback_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
                    ((1, 100),),
                ),
                (
                    "SELECT id, multiplier FROM dev__dev.amount_multipliers ORDER BY id",
                    ((1, 1),),
                ),
                (
                    "SELECT id, amount_cents FROM dev__dev.stg_orders ORDER BY id",
                    ((1, 100),),
                ),
            ),
            expected_checkpoint_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_rolling_back_then_it_restores_checkpointed_seed_refs_and_views(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_seed_refs",
        repo_files=build_virtual_multi_seed_lifecycle_repo_files(amount_cents=100, multiplier=1),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    initial_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    checkpoint_id: str = str(
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints "
                "WHERE virtual_environment_name = 'dev' ORDER BY created_at LIMIT 1"
            ),
        )[0][0]
    )
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "id,amount_cents\n1,200\n", encoding="utf-8"
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
    ) == [(1, 200)]
    show_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "show", checkpoint_id),
        project_dir=project_dir,
    )
    assert show_result.returncode == 0, show_result.stderr
    assert "Seed refs" in show_result.stdout
    assert "order_amounts" in show_result.stdout
    diff_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "diff", checkpoint_id),
        project_dir=project_dir,
    )
    assert diff_result.returncode == 0, diff_result.stderr
    assert "changed seeds    1" in diff_result.stdout

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    rolled_back_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    assert rolled_back_seed_ref_rows == initial_seed_ref_rows


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="partial rollback restores upstream seed refs and views",
            rollback_command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-rollback",
            ),
            expected_rollback_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
                    ((1, 100),),
                ),
            ),
            expected_checkpoint_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_partial_rollback_then_restores_upstream_seed_refs_and_views(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_partial_seed_refs",
        repo_files=build_virtual_multi_seed_lifecycle_repo_files(amount_cents=100, multiplier=1),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    initial_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "id,amount_cents\n1,200\n", encoding="utf-8"
    )
    (project_dir / "seeds" / "amount_multipliers.csv").write_text(
        "id,multiplier\n1,2\n", encoding="utf-8"
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stdout + rollback_result.stderr
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    rolled_back_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    assert rolled_back_seed_ref_rows == initial_seed_ref_rows


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="whole VDE rollback restores checkpointed function definitions",
            rollback_command=("--no-color", "rollback"),
            expected_rollback_fragments=(
                "\u2713 Virtual rollback complete",
                "status               finalized",
            ),
            expected_query_results=(
                ("SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large", ((False,),)),
            ),
            expected_checkpoint_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_function_change_when_rolling_back_then_it_restores_checkpointed_definition(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_function_definition",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 7 AS id")
        | {
            "models/fact_orders.sql": (
                "MODEL (materialized view);\n\n"
                'SELECT __udf("is_large_order")(id) AS is_large FROM __ref("stg_orders")\n'
            ),
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change full);\n\n"
                "amount > 9\n"
            ),
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == [(False,)]

    (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 5\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == [(True,)]
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    checkpoint_function_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_checkpoint_function_refs",
    )

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert int(checkpoint_rows[0][0]) == test_case.expected_checkpoint_count
    assert int(checkpoint_function_ref_rows[0][0]) == 2
    assert rollback_result.returncode == 0, rollback_result.stderr
    for fragment in test_case.expected_rollback_fragments:
        assert fragment in rollback_result.stdout
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualExplicitCheckpointRollbackE2ETestCase(
            description="explicit checkpoint restores selected checkpoint",
            rollback_command_prefix=("--no-color", "rollback", "--checkpoint-id"),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_checkpoint_when_rolling_back_then_it_restores_that_checkpoint(
    test_case: VirtualExplicitCheckpointRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_explicit_checkpoint",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    initial_checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints "
            "ORDER BY created_at ASC, checkpoint_id ASC"
        ),
    )
    initial_checkpoint_id: str = str(initial_checkpoint_rows[0][0])
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 3 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(*test_case.rollback_command_prefix, initial_checkpoint_id),
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    assert f"checkpoint           {initial_checkpoint_id}" in rollback_result.stdout
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPartialRollbackE2ETestCase(
            description="partial rollback requires override and marks VDE working",
            blocked_command=("--no-color", "rollback", "--select", "stg_orders"),
            allowed_command=(
                "--no-color",
                "rollback",
                "--select",
                "stg_orders",
                "--allow-partial-rollback",
            ),
            expected_blocked_stderr_fragments=(
                "rollback would leave target virtual environment working",
            ),
            expected_allowed_stdout_fragments=(
                "status               active",
                "rolled back models   1",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.stg_orders ORDER BY id", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_rollback_when_allowed_then_it_marks_vde_working(
    test_case: VirtualPartialRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_partial",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    blocked_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.blocked_command,
        project_dir=project_dir,
    )
    assert blocked_result.returncode == 1
    for fragment in test_case.expected_blocked_stderr_fragments:
        assert fragment in blocked_result.stderr

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.allowed_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    for fragment in test_case.expected_allowed_stdout_fragments:
        assert fragment in rollback_result.stdout
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPartialRollbackE2ETestCase(
            description="partial rollback can include stale required upstreams",
            blocked_command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--allow-partial-rollback",
            ),
            allowed_command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-rollback",
            ),
            expected_blocked_stderr_fragments=(
                "selected rollback scope is missing stale required upstream models",
                "stg_orders",
            ),
            expected_allowed_stdout_fragments=(
                "status               finalized",
                "rolled back models   2",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_rollback_missing_stale_upstreams_when_including_them_then_it_succeeds(
    test_case: VirtualPartialRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_include_stale_upstreams",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    blocked_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.blocked_command,
        project_dir=project_dir,
    )
    assert blocked_result.returncode == 1
    for fragment in test_case.expected_blocked_stderr_fragments:
        assert fragment in blocked_result.stderr

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.allowed_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    for fragment in test_case.expected_allowed_stdout_fragments:
        assert fragment in rollback_result.stdout
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPartialRollbackE2ETestCase(
            description="partial rollback matches checkpoint when workspace changed",
            blocked_command=(),
            allowed_command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
            ),
            expected_blocked_stderr_fragments=(),
            expected_allowed_stdout_fragments=(
                "status               finalized",
                "rolled back models   2",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_rollback_matches_checkpoint_when_workspace_changed_then_no_override_needed(
    test_case: VirtualPartialRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_stale_workspace",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 3 AS id\n",
        encoding="utf-8",
    )

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.allowed_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stdout + rollback_result.stderr
    fragment: str
    for fragment in test_case.expected_allowed_stdout_fragments:
        assert fragment in rollback_result.stdout
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
