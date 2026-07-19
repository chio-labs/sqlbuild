from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualPromoteE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    build_virtual_multi_seed_lifecycle_repo_files,
    build_virtual_seed_lifecycle_repo_files,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
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
        VirtualPromoteE2ETestCase(
            description="whole VDE promotion swaps target refs and views",
            promote_command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=(
                "Virtual promotion complete",
                "pr -> dev",
                "target status          finalized",
                "promoted models        3",
                "remaining stale models 0",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((2,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_env_when_promoting_then_it_updates_target_refs_and_views(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_whole",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stderr
    fragment: str
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints "
            "WHERE virtual_environment_name = 'dev'"
        ),
    )
    assert len(checkpoint_rows) == 2
    operation_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT operation_type, status, virtual_environment_name "
            "FROM sqlbuild_state.state_operations ORDER BY created_at DESC LIMIT 1"
        ),
    )
    assert operation_rows == [("promote", "succeeded", "dev")]
    operation_event_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT action, status FROM sqlbuild_state.state_operation_events ORDER BY created_at"
        ),
    )
    assert operation_event_rows[-2:] == [("start", "running"), ("finish", "succeeded")]
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
        VirtualPromoteE2ETestCase(
            description="whole VDE promotion carries seed refs and views",
            promote_command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
                    ((1, 200),),
                ),
                (
                    "SELECT id, amount_cents FROM dev__dev.stg_orders ORDER BY id",
                    ((1, 200),),
                ),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_promoting_then_it_updates_destination_seed_refs_and_views(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_seed_refs",
        repo_files=build_virtual_seed_lifecycle_repo_files(amount_cents=100),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "id,amount_cents\n1,200\n", encoding="utf-8"
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
        ).returncode
        == 0
    )

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT virtual_environment_name, node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name IN ('dev', 'pr') AND node_type = 'seed' "
            "ORDER BY virtual_environment_name"
        ),
    )
    assert len(seed_ref_rows) == 2
    assert seed_ref_rows[0][2] == seed_ref_rows[1][2]
    checkpoint_seed_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT seed_name FROM sqlbuild_state.virtual_environment_checkpoint_seed_refs "
            "WHERE seed_name = 'order_amounts'"
        ),
    )
    assert checkpoint_seed_rows


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="partial promotion carries upstream seed refs and views",
            promote_command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            expected_promote_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
                    ((1, 200),),
                ),
                (
                    "SELECT id, multiplier FROM dev__dev.amount_multipliers ORDER BY id",
                    ((1, 2),),
                ),
                ("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_partially_promoting_then_it_updates_upstream_seed_refs_and_views(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_partial_seed_refs",
        repo_files=build_virtual_multi_seed_lifecycle_repo_files(amount_cents=100, multiplier=1),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "id,amount_cents\n1,200\n", encoding="utf-8"
    )
    (project_dir / "seeds" / "amount_multipliers.csv").write_text(
        "id,multiplier\n1,2\n", encoding="utf-8"
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
        ).returncode
        == 0
    )

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stdout + promote_result.stderr
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT virtual_environment_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name IN ('dev', 'pr') "
            "AND node_type = 'seed' "
            "AND node_name IN ('order_amounts', 'amount_multipliers') "
            "ORDER BY node_name, virtual_environment_name"
        ),
    )
    assert len(seed_ref_rows) == 4
    assert seed_ref_rows[0][1] == seed_ref_rows[1][1]
    assert seed_ref_rows[2][1] == seed_ref_rows[3][1]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="whole VDE promotion carries function definitions",
            promote_command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=(
                "Virtual promotion complete",
                "pr -> dev",
                "target status          finalized",
            ),
            expected_query_results=(
                ("SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large", ((True,),)),
                ("SELECT dev__dev.is_large_order(7)", ((True,),)),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_function_change_when_promoting_then_it_publishes_target_function_definition(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_function_definition",
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
        sql="SELECT dev__dev.is_large_order(7)",
    ) == [(False,)]

    (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 5\n",
        encoding="utf-8",
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
        ).returncode
        == 0
    )
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__pr.fact_orders ORDER BY is_large",
    ) == [(True,)]
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == [(False,)]

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stderr
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
    function_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type IN ('udf', 'table_fn')"
        ),
    )
    assert len(function_ref_rows) == 1
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="finalized source promotes after workspace changes again",
            promote_command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=(
                "Virtual promotion complete",
                "target status          finalized",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.stg_orders ORDER BY id", ((2,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_finalized_source_vde_when_workspace_changes_again_then_whole_promotion_succeeds(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_finalized_stale_workspace",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 3 AS id\n",
        encoding="utf-8",
    )

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stdout + promote_result.stderr
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="partial promotion preserves unrelated current source identity",
            promote_command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "independent",
            ),
            expected_promote_fragments=(
                "Virtual promotion complete",
                "promoted models        1",
            ),
            expected_query_results=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unrelated_source_model_when_promoting_partial_then_current_identity_does_not_block(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_source_identity",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    schema: raw\n"
                "    table: raw_orders\n"
                "    freshness:\n"
                "      strategy: column\n"
                "      column: data_version\n"
                "      type: integer\n"
            ),
            "models/source_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
            "models/independent.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "CREATE SCHEMA raw; "
            "CREATE TABLE raw.raw_orders (id INTEGER, data_version INTEGER); "
            "INSERT INTO raw.raw_orders VALUES (1, 1)"
        ),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    dev_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert dev_build_result.returncode == 0, dev_build_result.stdout + dev_build_result.stderr
    (project_dir / "models" / "independent.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    pr_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert pr_build_result.returncode == 0, pr_build_result.stdout + pr_build_result.stderr

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stdout + promote_result.stderr
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout, promote_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="partial promotion requires explicit working target acceptance",
            blocked_command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
            ),
            promote_command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            expected_blocked_fragments=(
                "promotion would leave target virtual environment working",
                "orders_rollup",
                "--allow-partial-promotion",
            ),
            expected_promote_fragments=(
                "target status          working",
                "promoted models        2",
                "remaining stale set: orders_rollup",
            ),
            expected_query_results=(
                ("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((2,),)),
                ("SELECT order_count FROM dev__dev.orders_rollup", ((1,),)),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_virtual_promotion_when_target_stays_working_then_it_requires_override(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_partial",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "models/orders_rollup.sql": (
                'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
            )
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr

    blocked_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.blocked_command,
        project_dir=project_dir,
    )
    assert blocked_result.returncode != 0
    blocked_output: str = blocked_result.stdout + blocked_result.stderr
    fragment: str
    for fragment in test_case.expected_blocked_fragments:
        assert fragment in blocked_output

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )
    assert promote_result.returncode == 0, promote_result.stderr
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
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
        VirtualPromoteE2ETestCase(
            description="standard mode promotion fails with mode error",
            promote_command=("promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=("promote requires virtual_environments = true",),
            expected_query_results=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_mode_project_when_promoting_then_it_fails_with_mode_error(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_promote_guard",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_promote_guard"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
            ),
            "models/stg_orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_promote_fragments:
        assert fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="missing promoted physical relation fails clearly",
            promote_command=(
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            expected_promote_fragments=("fact_orders",),
            expected_query_results=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_promoted_physical_relation_is_missing_when_promoting_then_it_fails_clearly(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_missing_physical",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr
    physical_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT schema_name, relation_name "
            "FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'model' AND artifact_name = 'fact_orders' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
    )
    assert physical_rows
    schema_name, relation_name = physical_rows[0]
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=f'DROP TABLE "{schema_name}"."{relation_name}"',
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_promote_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="target VDE lock blocks promotion",
            promote_command=("promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=("virtual environment 'dev' is locked",),
            expected_query_results=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_virtual_environment_lock_when_promoting_then_it_fails_clearly(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_locked_target",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) "
            "VALUES ('virtual_env:dev', 'test-owner', TIMESTAMP '2999-01-01', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_promote_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="interrupted promotion records failed operation",
            promote_command=("promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=("simulated promote view refresh failure",),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_view_refresh_failure_when_promoting_then_operation_is_marked_failed(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_failed_operation",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "adapters/failing_duckdb.py": (
                "from typing import Any\n"
                "from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder\n"
                "from sqlbuild.adapter.contract.exceptions import AdapterUserError\n"
                "from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter\n\n"
                "class FailingDuckDbAdapter(DuckDbAdapter):\n"
                "    adapter_name = 'failing_duckdb'\n\n"
                "    def create_view_as(\n"
                "        self,\n"
                "        connection: Any,\n"
                "        *,\n"
                "        destination: str,\n"
                "        sql: str,\n"
                "        statement_recorder: StatementRecorder,\n"
                "    ) -> None:\n"
                "        raise AdapterUserError('simulated promote view refresh failure')\n"
            )
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
        ).returncode
        == 0
    )
    (project_dir / "sqlbuild_local.toml").write_text(
        'adapter = "failing_duckdb"\n\n'
        "[connection]\n"
        f'database = "{project_dir / "warehouse.duckdb"}"\n'
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert test_case.expected_promote_fragments[0] in (result.stdout + result.stderr)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT operation_type, status, virtual_environment_name "
            "FROM sqlbuild_state.state_operations WHERE operation_type = 'promote'"
        ),
    ) == [("promote", "failed", "dev")]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT status, message FROM sqlbuild_state.state_operation_events "
            "WHERE operation_id LIKE 'promote:%' ORDER BY created_at DESC LIMIT 1"
        ),
    ) == [("failed", test_case.expected_promote_fragments[0])]
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description=(
                "working source blocks whole promotion but allows coherent partial promotion"
            ),
            blocked_command=("promote", "--from", "pr", "--to", "dev"),
            promote_command=(
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            expected_blocked_fragments=(
                "whole-VDE promotion requires a finalized source virtual environment",
                "--select",
            ),
            expected_promote_fragments=("Virtual promotion complete", "target status"),
            expected_query_results=(
                ("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((2,),)),
                ("SELECT order_count FROM dev__dev.orders_rollup", ((1,),)),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_working_source_vde_when_promoting_then_whole_blocks_and_partial_succeeds(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_working_source",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "models/orders_rollup.sql": (
                'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
            )
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "build",
            "--virtual-env",
            "pr",
            "--select",
            "fact_orders",
            "--include-stale-upstreams",
        ),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr

    blocked_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.blocked_command,
        project_dir=project_dir,
    )
    assert blocked_result.returncode == 1, blocked_result.stdout + blocked_result.stderr
    blocked_output: str = blocked_result.stdout + blocked_result.stderr
    fragment: str
    for fragment in test_case.expected_blocked_fragments:
        assert fragment in blocked_output

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )
    assert promote_result.returncode == 0, promote_result.stdout + promote_result.stderr
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)
