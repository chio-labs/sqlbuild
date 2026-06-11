from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.load.helpers import (
    build_loader_waffle_shop_project_files,
    build_schema_behavior_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    assert_optional_local_replay_rows,
    build_real_warehouse_local_replay_project_files,
    maybe_corrupt_scenario_snapshot_dialect,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    build_current_check_customers_model_sql,
    build_current_customers_model_sql,
    build_current_delete_customers_model_sql,
    build_historical_check_daily_model_sql,
    build_historical_timestamp_extracts_model_sql,
    build_real_warehouse_existing_snapshot_project_files,
    build_real_warehouse_snapshot_project_files,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
    stringify_warehouse_rows,
)
from tests.e2e.src.sqlbuild.cli.commands.main.sqlserver._test_types import (
    SqlServerBuildE2ETestCase,
    SqlServerIntermediateDagStrategyE2ETestCase,
    SqlServerJanitorDetachedVdeE2ETestCase,
    SqlServerLoaderWaffleShopE2ETestCase,
    SqlServerReconcileE2ETestCase,
    SqlServerScenarioLocalReplayE2ETestCase,
    SqlServerSnapshotApplyE2ETestCase,
    SqlServerSnapshotE2ETestCase,
    SqlServerSourceDeferralE2ETestCase,
    SqlServerSourceLoaderDagE2ETestCase,
    SqlServerSourceLoaderE2ETestCase,
    SqlServerSourceLoaderStrategiesE2ETestCase,
    SqlServerVirtualLifecycleE2ETestCase,
    SqlServerVirtualSeedE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.sqlserver.helpers import (
    adapt_sqlserver_project_files,
    adapt_sqlserver_sql,
    assert_current_sqlserver_snapshot_rows_from_case,
    assert_sqlserver_snapshot_apply_rows,
    assert_sqlserver_snapshot_matrix_rows,
    build_sqlserver_config,
    build_sqlserver_project_toml,
    build_sqlserver_source_deferral_project_toml,
    build_sqlserver_virtual_project_toml,
    build_unique_schema_name,
    cleanup_sqlserver_schema,
    ensure_sqlserver_schema_ready,
    execute_sqlserver_sql,
    fetch_sqlserver_rows,
    prepare_sqlserver_source_loader_strategies,
    prepare_sqlserver_waffle_shop,
    relation_name,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerBuildE2ETestCase(
            description="waffle shop full build succeeds on SQL Server",
            command=("--no-color", "build", "--concurrency", "4"),
            expected_table_name="fact_orders",
            expected_row_count=10,
            expected_stdout_fragments=("Execution", "OK"),
        )
    ],
    ids=["waffle shop full build succeeds on SQL Server"],
)
def test_given_waffle_shop_when_running_full_build_on_sqlserver_then_expected_table_exists(
    tmp_path: Path,
    test_case: SqlServerBuildE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_sqlserver_waffle_shop(tmp_path=tmp_path, config=config)
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name=test_case.expected_table_name)}"
            ),
            config=config,
        )
        assert int(str(rows[0][0])) == test_case.expected_row_count
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerBuildE2ETestCase(
            description="direct changes only build prunes unchanged SQL Server model",
            expected_table_name="orders",
            expected_row_count=1,
            expected_stdout_fragments=("Plan ready (0 selected)", "TOTAL=0"),
        )
    ],
    ids=["direct changes only build prunes unchanged SQL Server model"],
)
def test_given_built_direct_project_when_building_changes_only_on_sqlserver_then_prunes_model(
    tmp_path: Path,
    test_case: SqlServerBuildE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_changes_only")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_changes_only",
        repo_files={
            "sqlbuild_project.toml": build_sqlserver_project_toml(
                project_name="sqlserver_changes_only",
                schema_name=schema_name,
                config=config,
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        },
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        initial_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

        changes_only_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--changes-only"),
            project_dir=project_dir,
        )

        assert changes_only_result.returncode == test_case.expected_return_code, (
            changes_only_result.stdout + changes_only_result.stderr
        )
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in changes_only_result.stdout, changes_only_result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name=test_case.expected_table_name)}"
            ),
            config=config,
        )
        assert int(str(rows[0][0])) == test_case.expected_row_count
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerVirtualSeedE2ETestCase(
            description="virtual seeded incremental build uses copy on sqlserver",
            expected_rows=(("1", "10"), ("2", "21"), ("3", "31")),
            expected_seed_strategy="copy",
        )
    ],
    ids=["virtual seeded incremental build uses copy on sqlserver"],
)
def test_given_virtual_incremental_change_when_building_on_sqlserver_then_seeds_with_copy(
    tmp_path: Path,
    test_case: SqlServerVirtualSeedE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_virtual_seed")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_virtual_seed",
        repo_files={
            "sqlbuild_project.toml": build_sqlserver_virtual_project_toml(
                project_name="sqlserver_virtual_seed",
                schema_name=schema_name,
                config=config,
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                f"    schema: {schema_name}\n"
                "    table: raw_orders\n"
            ),
            "models/orders.sql": (
                "MODEL (\n"
                "  materialized incremental,\n"
                "  incremental_strategy delete_insert,\n"
                "  cursor ordered_at,\n"
                "  cursor_type timestamp,\n"
                "  cursor_grain day,\n"
                "  replay_on_change bounded-7d\n"
                ");\n\n"
                "SELECT id, ordered_at, amount_cents + 0 AS amount_cents\n"
                'FROM __source("raw_orders")\n'
            ),
        },
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        execute_sqlserver_sql(
            sql=(
                f"CREATE TABLE {relation_name(schema_name=schema_name, name='raw_orders')} ("
                "id INT, ordered_at DATETIME2, amount_cents INT)"
            ),
            config=config,
        )
        execute_sqlserver_sql(
            sql=(
                f"INSERT INTO {relation_name(schema_name=schema_name, name='raw_orders')} VALUES "
                "(1, '2026-01-01T00:00:00', 10), "
                "(2, '2026-01-02T00:00:00', 20)"
            ),
            config=config,
        )
        assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "models" / "orders.sql").write_text(
            (
                "MODEL (\n"
                "  materialized incremental,\n"
                "  incremental_strategy delete_insert,\n"
                "  cursor ordered_at,\n"
                "  cursor_type timestamp,\n"
                "  cursor_grain day,\n"
                "  replay_on_change bounded-7d\n"
                ");\n\n"
                "SELECT id, ordered_at, amount_cents + 1 AS amount_cents\n"
                'FROM __source("raw_orders")\n'
            ),
            encoding="utf-8",
        )
        execute_sqlserver_sql(
            sql=(
                f"INSERT INTO {relation_name(schema_name=schema_name, name='raw_orders')} "
                "VALUES (3, '2026-01-03T00:00:00', 30)"
            ),
            config=config,
        )

        build_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "build",
                "--start-cursor-ts",
                "2026-01-02T00:00:00",
                "--end-cursor-ts",
                "2026-01-04T00:00:00",
            ),
            project_dir=project_dir,
        )

        assert build_result.returncode == test_case.expected_return_code, (
            build_result.stdout + build_result.stderr
        )
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            sql=(
                f"SELECT id, amount_cents FROM "
                f"{relation_name(schema_name=f'{schema_name}__dev', name='orders')} "
                "ORDER BY id"
            ),
            config=config,
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
        assert query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT seed_strategy FROM sqlbuild_state.physical_relation_ancestry "
                "WHERE model_name = 'orders'"
            ),
        ) == [(test_case.expected_seed_strategy,)]
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=f"{schema_name}__dev", config=config)
        cleanup_sqlserver_schema(schema_name=f"{schema_name}__sqb_physical", config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerReconcileE2ETestCase(
            description="reconcile repair-view recreates sqlserver logical view",
            expected_rows=(("1",),),
            expected_stdout_fragments=(
                "Repair",
                "model   orders",
                "VDE     dev",
                "action  recreate logical view from state",
                "result  repaired",
            ),
        )
    ],
    ids=["reconcile repair-view recreates sqlserver logical view"],
)
def test_given_missing_logical_view_when_repairing_on_sqlserver_then_view_is_recreated(
    tmp_path: Path,
    test_case: SqlServerReconcileE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_virtual_reconcile")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_virtual_reconcile",
        repo_files={
            "sqlbuild_project.toml": build_sqlserver_virtual_project_toml(
                project_name="sqlserver_virtual_reconcile",
                schema_name=schema_name,
                config=config,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        execute_sqlserver_sql(
            sql=f"DROP VIEW {relation_name(schema_name=f'{schema_name}__dev', name='orders')}",
            config=config,
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            sql=(
                f"SELECT id FROM {relation_name(schema_name=f'{schema_name}__dev', name='orders')} "
                "ORDER BY id"
            ),
            config=config,
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=f"{schema_name}__dev", config=config)
        cleanup_sqlserver_schema(schema_name=f"{schema_name}__sqb_physical", config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerReconcileE2ETestCase(
            description="reconcile attach rebinds sqlserver logical view",
            expected_rows=(("2",),),
            expected_stdout_fragments=("Attach", "model     orders", "result    attached"),
        )
    ],
    ids=["reconcile attach rebinds sqlserver logical view"],
)
def test_given_tracked_physical_relation_when_attaching_on_sqlserver_then_view_is_rebound(
    tmp_path: Path,
    test_case: SqlServerReconcileE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_virtual_attach")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_virtual_attach",
        repo_files={
            "sqlbuild_project.toml": build_sqlserver_virtual_project_toml(
                project_name="sqlserver_virtual_attach",
                schema_name=schema_name,
                config=config,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "models" / "orders.sql").write_text(
            "MODEL ();\n\nSELECT 2 AS id\n",
            encoding="utf-8",
        )
        assert (
            run_sqb(
                command=("--no-color", "build", "--virtual-env", "pr"),
                project_dir=project_dir,
            ).returncode
            == 0
        )
        _database_name, physical_schema_name, physical_relation_name = query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT database_name, schema_name, relation_name "
                "FROM sqlbuild_state.physical_relations "
                "WHERE model_name = 'orders' ORDER BY updated_at DESC LIMIT 1"
            ),
        )[0]
        physical_relation: str = f'"{physical_schema_name}"."{physical_relation_name}"'

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "attach",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
                "--physical-relation",
                physical_relation,
                "--auto-approve",
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            sql=(
                f"SELECT id FROM {relation_name(schema_name=f'{schema_name}__dev', name='orders')} "
                "ORDER BY id"
            ),
            config=config,
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=f"{schema_name}__dev", config=config)
        cleanup_sqlserver_schema(schema_name=f"{schema_name}__pr", config=config)
        cleanup_sqlserver_schema(schema_name=f"{schema_name}__sqb_physical", config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerVirtualLifecycleE2ETestCase(
            description="adopt and detach preserve sqlserver logical table",
            expected_rows=(("1",),),
            expected_stdout_fragments=(
                "Adopted 1 models into virtual environment dev.",
                "Detached 1 models from virtual environment dev.",
            ),
        )
    ],
    ids=["adopt and detach preserve sqlserver logical table"],
)
def test_given_stateless_table_when_adopting_and_detaching_on_sqlserver_then_table_is_preserved(
    tmp_path: Path,
    test_case: SqlServerVirtualLifecycleE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_virtual_lifecycle")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_virtual_lifecycle",
        repo_files={
            "sqlbuild_project.toml": build_sqlserver_virtual_project_toml(
                project_name="sqlserver_virtual_lifecycle",
                schema_name=schema_name,
                config=config,
                unsuffixed_virtual_env="dev",
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        execute_sqlserver_sql(
            sql=f"CREATE TABLE {relation_name(schema_name=schema_name, name='orders')} (id INT)",
            config=config,
        )
        execute_sqlserver_sql(
            sql=f"INSERT INTO {relation_name(schema_name=schema_name, name='orders')} VALUES (1)",
            config=config,
        )
        assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
        adopt_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "adopt"),
            project_dir=project_dir,
            input_text="adopt dev\n",
        )
        detach_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "detach", "--allow-copy"),
            project_dir=project_dir,
            input_text="detach dev\n",
        )

        assert adopt_result.returncode == test_case.expected_return_code, (
            adopt_result.stdout + adopt_result.stderr
        )
        assert detach_result.returncode == test_case.expected_return_code, (
            detach_result.stdout + detach_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in adopt_result.stdout + detach_result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            sql=(
                f"SELECT id FROM {relation_name(schema_name=schema_name, name='orders')} "
                "ORDER BY id"
            ),
            config=config,
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=f"{schema_name}__sqb_physical", config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerJanitorDetachedVdeE2ETestCase(
            description="janitor prunes sqlserver detached VDE refs and physical versions",
            expected_stdout_fragments=(
                "eligible for deletion",
                "detached VDEs pruned",
                "Eligible detached VDEs",
                "dev  detached virtual environment",
                "state items",
            ),
            expected_virtual_environment_count_after=0,
            expected_ref_count_after=0,
        )
    ],
    ids=["janitor prunes sqlserver detached VDE refs and physical versions"],
)
def test_given_detached_vde_when_running_janitor_on_sqlserver_then_refs_are_pruned(
    tmp_path: Path,
    test_case: SqlServerJanitorDetachedVdeE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_virtual_janitor")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_virtual_janitor",
        repo_files={
            "sqlbuild_project.toml": (
                build_sqlserver_virtual_project_toml(
                    project_name="sqlserver_virtual_janitor",
                    schema_name=schema_name,
                    config=config,
                    unsuffixed_virtual_env="dev",
                )
                + "\n[janitor]\n"
                + "enabled = true\n"
                + "retention_days = 0\n"
                + "delete_tracked_only = false\n"
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        execute_sqlserver_sql(
            sql=f"CREATE TABLE {relation_name(schema_name=schema_name, name='orders')} (id INT)",
            config=config,
        )
        execute_sqlserver_sql(
            sql=f"INSERT INTO {relation_name(schema_name=schema_name, name='orders')} VALUES (1)",
            config=config,
        )
        assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
        assert (
            run_sqb(
                command=("--no-color", "state", "adopt", "--allow-copy"),
                project_dir=project_dir,
                input_text="adopt dev\n",
            ).returncode
            == 0
        )
        assert (
            run_sqb(
                command=("--no-color", "state", "detach", "--allow-copy"),
                project_dir=project_dir,
                input_text="detach dev\n",
            ).returncode
            == 0
        )

        janitor_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve"),
            project_dir=project_dir,
        )

        assert janitor_result.returncode == test_case.expected_return_code, (
            janitor_result.stdout + janitor_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in janitor_result.stdout
        assert query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environments",
        ) == [(test_case.expected_virtual_environment_count_after,)]
        assert query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_model_refs",
        ) == [(test_case.expected_ref_count_after,)]
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=f"{schema_name}__sqb_physical", config=config)


SQLSERVER_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES: list[SqlServerScenarioLocalReplayE2ETestCase] = [
    SqlServerScenarioLocalReplayE2ETestCase(
        description="captures SQL Server fixtures and replays transpilable SQL locally",
        model_sql=(
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  customer_id,\n"
            "  CAST(CAST(event_ts AS DATE) AS DATETIME2) AS event_day,\n"
            "  SUM(CASE WHEN amount_cents >= 1000 THEN amount_cents ELSE 0 END)"
            " AS large_amount_cents,\n"
            "  COUNT(*) AS event_count\n"
            'FROM __source("raw_events")\n'
            "GROUP BY customer_id, CAST(CAST(event_ts AS DATE) AS DATETIME2)\n"
        ),
        scenario_sql=(
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_events AS (\n"
            "  SELECT 10 AS customer_id, CAST('2026-01-01 08:15:00' AS DATETIME2)"
            " AS event_ts, 1500 AS amount_cents\n"
            "  UNION ALL\n"
            "  SELECT 10 AS customer_id, CAST('2026-01-01 10:30:00' AS DATETIME2)"
            " AS event_ts, 500 AS amount_cents\n"
            "),\n"
            "__expected__event_rollup AS (\n"
            "  SELECT 10 AS customer_id,"
            " CAST(CAST('2026-01-01 00:00:00' AS DATE) AS DATETIME2) AS event_day,"
            " 1500 AS large_amount_cents, 2 AS event_count\n"
            ")\n"
            "SELECT 1\n"
        ),
        expected_stdout_fragments=(
            "transpilable_event_rollup",
            "PASS",
            "PASS=1  FAIL=0  ERROR=0  SKIP=0  TOTAL=1",
        ),
        expected_local_rows=((10, 1500, 2),),
        local_rows_sql=(
            "SELECT customer_id, large_amount_cents, event_count "
            "FROM __sqb_local__model__event_rollup ORDER BY customer_id"
        ),
    ),
    SqlServerScenarioLocalReplayE2ETestCase(
        description="reports SQL Server local transpilation failures as X607",
        scenario_name="local_transpile_error",
        model_sql=(
            "MODEL (materialized table);\n\n"
            "SELECT customer_id, amount_cents\n"
            'FROM __source("raw_events")\n'
        ),
        scenario_sql=(
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_events AS (\n"
            "  SELECT 10 AS customer_id, 1500 AS amount_cents\n"
            "),\n"
            "__expected__event_rollup AS (\n"
            "  SELECT 10 AS customer_id, 1500 AS amount_cents\n"
            ")\n"
            "SELECT 1\n"
        ),
        expected_stdout_fragments=(
            "local_transpile_error",
            "ERROR",
            "error[X607]",
            "PASS=0  FAIL=0  ERROR=1  SKIP=0  TOTAL=1",
        ),
        expected_return_code=1,
        corrupt_capture_dialect=True,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SQLSERVER_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES,
    ids=[case.description for case in SQLSERVER_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES],
)
def test_given_sqlserver_scenario_capture_when_replaying_locally_then_transpilable_sql_passes(
    tmp_path: Path,
    test_case: SqlServerScenarioLocalReplayE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_scenario_local")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_scenario_local_replay",
        repo_files=build_real_warehouse_local_replay_project_files(
            project_toml=build_sqlserver_project_toml(
                project_name="sqlserver_scenario_local_replay",
                schema_name=schema_name,
                config=config,
            ),
            model_sql=test_case.model_sql,
            scenario_sql=test_case.scenario_sql,
            scenario_name=test_case.scenario_name,
        ),
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        capture_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "scenario", "capture", test_case.scenario_name),
            project_dir=project_dir,
        )
        assert capture_result.returncode == 0, capture_result.stdout + capture_result.stderr
        maybe_corrupt_scenario_snapshot_dialect(
            project_dir=project_dir,
            scenario_name=test_case.scenario_name,
            enabled=test_case.corrupt_capture_dialect,
        )

        replay_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "scenario", "test", test_case.scenario_name, "--local"),
            project_dir=project_dir,
        )

        assert replay_result.returncode == test_case.expected_return_code, (
            replay_result.stdout + replay_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in replay_result.stdout
        assert_optional_local_replay_rows(
            project_dir=project_dir,
            scenario_name=test_case.scenario_name,
            local_rows_sql=test_case.local_rows_sql,
            expected_local_rows=test_case.expected_local_rows,
        )
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerSourceLoaderE2ETestCase(
            description="source loader build writes and reads SQL Server rows",
            expected_rows=(("7", "loaded-dev"),),
        )
    ],
    ids=["source loader build writes and reads SQL Server rows"],
)
def test_given_source_loader_project_when_building_on_sqlserver_then_model_reads_loaded_rows(
    tmp_path: Path,
    test_case: SqlServerSourceLoaderE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_e2e_loader")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_source_loader",
        repo_files={
            "sqlbuild_project.toml": build_sqlserver_project_toml(
                project_name="sqlserver_source_loader",
                schema_name=schema_name,
                config=config,
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                "        type: NVARCHAR(100)\n"
            ),
            "loaders/raw_orders.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 7, 'status': 'loaded-dev'}]\n"
            ),
            "models/stg_orders.sql": (
                'MODEL (materialized table);\n\nSELECT order_id, status FROM __source("raw_orders")'
            ),
        },
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--select", "stg_orders"),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT order_id, status FROM "
                f"{relation_name(schema_name=schema_name, name='stg_orders')} "
                "ORDER BY order_id"
            ),
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerSourceDeferralE2ETestCase(
            description="SQL Server loader writes dev while model reads prod deferred source",
            expected_model_rows=(("99", "prod-source"),),
            expected_loader_rows=(("7", "loaded-dev"),),
        )
    ],
    ids=["SQL Server loader writes dev while model reads prod deferred source"],
)
def test_given_source_deferral_env_when_building_on_sqlserver_then_reads_prod_and_writes_dev(
    tmp_path: Path,
    test_case: SqlServerSourceDeferralE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    dev_schema_name: str = build_unique_schema_name(prefix="sqlbuild_defer_dev")
    prod_schema_name: str = build_unique_schema_name(prefix="sqlbuild_defer_prod")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_source_deferral",
        repo_files={
            "sqlbuild_project.toml": build_sqlserver_source_deferral_project_toml(
                project_name="sqlserver_source_deferral",
                dev_schema_name=dev_schema_name,
                prod_schema_name=prod_schema_name,
                config=config,
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                "        type: NVARCHAR(100)\n"
            ),
            "loaders/raw_orders.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 7, 'status': 'loaded-dev'}]\n"
            ),
            "models/stg_orders.sql": (
                'MODEL (materialized table);\n\nSELECT order_id, status FROM __source("raw_orders")'
            ),
        },
    )
    ensure_sqlserver_schema_ready(schema_name=dev_schema_name, config=config)
    ensure_sqlserver_schema_ready(schema_name=prod_schema_name, config=config)

    try:
        execute_sqlserver_sql(
            config=config,
            sql=(
                f"CREATE TABLE {relation_name(schema_name=prod_schema_name, name='raw_orders')} "
                "(order_id INT, status NVARCHAR(100))"
            ),
        )
        execute_sqlserver_sql(
            config=config,
            sql=(
                f"INSERT INTO {relation_name(schema_name=prod_schema_name, name='raw_orders')} "
                "VALUES (99, 'prod-source')"
            ),
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--select", "stg_orders"),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        model_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT order_id, status FROM "
                f"{relation_name(schema_name=dev_schema_name, name='stg_orders')} "
                "ORDER BY order_id"
            ),
        )
        loader_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT order_id, status FROM "
                f"{relation_name(schema_name=dev_schema_name, name='raw_orders')} "
                "ORDER BY order_id"
            ),
        )
        assert stringify_warehouse_rows(model_rows) == test_case.expected_model_rows
        assert stringify_warehouse_rows(loader_rows) == test_case.expected_loader_rows
    finally:
        cleanup_sqlserver_schema(schema_name=dev_schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=prod_schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerLoaderWaffleShopE2ETestCase(
            description="loader focused waffle shop grows across repeated SQL Server builds",
            expected_rows=(
                ("1", "pro", "650", "1"),
                ("2", "plus", "3750", "2"),
                ("3", "enterprise", "1300", "1"),
            ),
            expected_event_count=4,
        )
    ],
    ids=["loader focused waffle shop grows across repeated SQL Server builds"],
)
def test_given_loader_waffle_shop_when_building_on_sqlserver_then_dag_grows_models(
    tmp_path: Path,
    test_case: SqlServerLoaderWaffleShopE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_load_waffle")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="loader_waffle_shop",
        repo_files=build_loader_waffle_shop_project_files(
            project_toml=build_sqlserver_project_toml(
                project_name="loader_waffle_shop",
                schema_name=schema_name,
                config=config,
            )
        ),
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        for _ in range(2):
            result: subprocess.CompletedProcess[str] = run_sqb(
                command=("--no-color", "build", "--select", "+customer_revenue"),
                project_dir=project_dir,
            )
            assert result.returncode == test_case.expected_return_code, (
                result.stdout + result.stderr
            )

        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT customer_id, plan_name, revenue_cents, order_count FROM "
                f"{relation_name(schema_name=schema_name, name='customer_revenue')} "
                "ORDER BY customer_id"
            ),
        )
        event_count_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name='__loader__fetch_order_events')}"
            ),
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
        assert int(str(event_count_rows[0][0])) == test_case.expected_event_count
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerSourceLoaderStrategiesE2ETestCase(
            description="source loader strategies apply expected rows on SQL Server",
            expected_countries=(("1", "US", "United States"), ("2", "CA", "Canada")),
            expected_webhook_event_counts=(("101", "signup", "2"), ("102", "checkout", "2")),
            expected_order_events=(("201", "1000"), ("202", "2500"), ("203", "3000")),
            expected_customers=(("1", "pro"), ("2", "trial"), ("3", "enterprise")),
            expected_loader_status=(("1", "loaded", "self_managed"),),
        )
    ],
    ids=["source loader strategies apply expected rows on SQL Server"],
)
def test_given_loader_strategy_project_when_loading_twice_on_sqlserver_then_write_modes_apply(
    tmp_path: Path,
    test_case: SqlServerSourceLoaderStrategiesE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_sqlserver_source_loader_strategies(
        tmp_path=tmp_path,
        config=config,
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        first_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "load", "--concurrency", "4"),
            project_dir=project_dir,
        )
        second_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "load", "--concurrency", "4"),
            project_dir=project_dir,
        )

        assert first_result.returncode == test_case.expected_return_code, (
            first_result.stdout + first_result.stderr
        )
        assert second_result.returncode == test_case.expected_return_code, (
            second_result.stdout + second_result.stderr
        )
        countries: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT country_id, country_code, country_name FROM "
                f"{relation_name(schema_name=schema_name, name='raw_countries')} "
                "ORDER BY country_id"
            ),
        )
        webhook_event_counts: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT event_id, event_name, COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name='raw_webhook_events')} "
                "GROUP BY event_id, event_name ORDER BY event_id"
            ),
        )
        order_events: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT event_id, amount_cents FROM "
                f"{relation_name(schema_name=schema_name, name='raw_order_events')} "
                "ORDER BY event_id"
            ),
        )
        customers: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT customer_id, plan_name FROM "
                f"{relation_name(schema_name=schema_name, name='raw_customers')} "
                "ORDER BY customer_id"
            ),
        )
        loader_status: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT status_id, status_name, loaded_by FROM "
                f"{relation_name(schema_name=schema_name, name='raw_loader_status')} "
                "ORDER BY status_id"
            ),
        )
        assert stringify_warehouse_rows(countries) == test_case.expected_countries
        assert stringify_warehouse_rows(webhook_event_counts) == (
            test_case.expected_webhook_event_counts
        )
        assert stringify_warehouse_rows(order_events) == test_case.expected_order_events
        assert stringify_warehouse_rows(customers) == test_case.expected_customers
        assert stringify_warehouse_rows(loader_status) == test_case.expected_loader_status
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerSourceLoaderDagE2ETestCase(
            description="chained source loader runs on SQL Server",
            command=("--no-color", "load", "--select", "+raw_events"),
            expected_rows=(("1", "loaded"), ("2", "loaded")),
        )
    ],
    ids=["chained source loader runs on SQL Server"],
)
def test_given_chained_loader_project_when_loading_on_sqlserver_then_runs_loader_dag(
    tmp_path: Path,
    test_case: SqlServerSourceLoaderDagE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_load_dag")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_dag_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                "        type: NVARCHAR(100)\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    return [{'event_id': 1}, {'event_id': 2}]\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                "    cursor = ctx.query(\n"
                "        f'SELECT event_id FROM {events.destination} ORDER BY event_id'\n"
                "    )\n"
                "    rows = cursor.fetchall()\n"
                "    return [{'event_id': row[0], 'status': 'loaded'} for row in rows]\n"
            ),
        ),
    )
    (project_dir / "sqlbuild_project.toml").write_text(
        build_sqlserver_project_toml(
            project_name="source_loader_dag_behavior",
            schema_name=schema_name,
            config=config,
        ),
        encoding="utf-8",
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT event_id, status FROM "
                f"{relation_name(schema_name=schema_name, name='raw_events')} "
                "ORDER BY event_id"
            ),
        )
        intermediate_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name='__loader__fetch_events')}"
            ),
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
        assert int(str(intermediate_rows[0][0])) == 2
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


SQLSERVER_INTERMEDIATE_DAG_STRATEGY_TEST_CASES: list[
    SqlServerIntermediateDagStrategyE2ETestCase
] = [
    SqlServerIntermediateDagStrategyE2ETestCase(
        description="SQL Server append intermediate accumulates rows across DAG loads",
        loader_py=(
            "from sqlbuild.loaders import loader\n\n"
            "@loader(write_strategy='append', cursor_column='load_seq', columns=[\n"
            "    {'name': 'event_id', 'type': 'INTEGER'},\n"
            "    {'name': 'amount', 'type': 'INTEGER'},\n"
            "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
            "])\n"
            "def fetch_events(ctx):\n"
            "    if ctx.current_cursor_value is None:\n"
            "        next_seq = 1\n"
            "    else:\n"
            "        next_seq = ctx.current_cursor_value + 1\n"
            "    return [\n"
            "        {'event_id': next_seq, 'amount': next_seq * 100, 'load_seq': next_seq}\n"
            "    ]\n\n"
            "@loader(depends_on=[fetch_events])\n"
            "def raw_events(ctx):\n"
            "    events = ctx.loader(fetch_events)\n"
            "    cursor = ctx.query(\n"
            "        f'SELECT event_id, amount FROM {events.destination} '\n"
            "        'ORDER BY event_id, amount'\n"
            "    )\n"
            "    rows = cursor.fetchall()\n"
            "    return [{'event_id': row[0], 'amount': row[1]} for row in rows]\n"
        ),
        expected_intermediate_rows=(("1", "100"), ("2", "200")),
        expected_terminal_rows=(("1", "100"), ("2", "200")),
    ),
    SqlServerIntermediateDagStrategyE2ETestCase(
        description="SQL Server merge intermediate updates and adds rows across DAG loads",
        loader_py=(
            "from sqlbuild.loaders import loader\n\n"
            "@loader(\n"
            "    write_strategy='merge',\n"
            "    unique_key='event_id',\n"
            "    cursor_column='load_seq',\n"
            "    columns=[\n"
            "        {'name': 'event_id', 'type': 'INTEGER'},\n"
            "        {'name': 'amount', 'type': 'INTEGER'},\n"
            "        {'name': 'load_seq', 'type': 'INTEGER'},\n"
            "    ],\n"
            ")\n"
            "def fetch_events(ctx):\n"
            "    if ctx.current_cursor_value is None:\n"
            "        return [\n"
            "            {'event_id': 1, 'amount': 100, 'load_seq': 1},\n"
            "            {'event_id': 2, 'amount': 200, 'load_seq': 1},\n"
            "        ]\n"
            "    return [\n"
            "        {'event_id': 1, 'amount': 150, 'load_seq': 2},\n"
            "        {'event_id': 3, 'amount': 300, 'load_seq': 2},\n"
            "    ]\n\n"
            "@loader(depends_on=[fetch_events])\n"
            "def raw_events(ctx):\n"
            "    events = ctx.loader(fetch_events)\n"
            "    cursor = ctx.query(\n"
            "        f'SELECT event_id, amount FROM {events.destination} '\n"
            "        'ORDER BY event_id, amount'\n"
            "    )\n"
            "    rows = cursor.fetchall()\n"
            "    return [{'event_id': row[0], 'amount': row[1]} for row in rows]\n"
        ),
        expected_intermediate_rows=(("1", "150"), ("2", "200"), ("3", "300")),
        expected_terminal_rows=(("1", "150"), ("2", "200"), ("3", "300")),
    ),
    SqlServerIntermediateDagStrategyE2ETestCase(
        description="SQL Server delete insert intermediate replaces cursor window across DAG loads",
        loader_py=(
            "from sqlbuild.loaders import loader\n\n"
            "@loader(write_strategy='delete_insert', cursor_column='load_seq', columns=[\n"
            "    {'name': 'event_id', 'type': 'INTEGER'},\n"
            "    {'name': 'amount', 'type': 'INTEGER'},\n"
            "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
            "])\n"
            "def fetch_events(ctx):\n"
            "    if ctx.current_cursor_value is None:\n"
            "        return [\n"
            "            {'event_id': 1, 'amount': 100, 'load_seq': 1},\n"
            "            {'event_id': 2, 'amount': 200, 'load_seq': 1},\n"
            "        ]\n"
            "    return [\n"
            "        {'event_id': 2, 'amount': 250, 'load_seq': 1},\n"
            "        {'event_id': 3, 'amount': 300, 'load_seq': 1},\n"
            "    ]\n\n"
            "@loader(depends_on=[fetch_events])\n"
            "def raw_events(ctx):\n"
            "    events = ctx.loader(fetch_events)\n"
            "    cursor = ctx.query(\n"
            "        f'SELECT event_id, amount FROM {events.destination} '\n"
            "        'ORDER BY event_id, amount'\n"
            "    )\n"
            "    rows = cursor.fetchall()\n"
            "    return [{'event_id': row[0], 'amount': row[1]} for row in rows]\n"
        ),
        expected_intermediate_rows=(("2", "250"), ("3", "300")),
        expected_terminal_rows=(("2", "250"), ("3", "300")),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SQLSERVER_INTERMEDIATE_DAG_STRATEGY_TEST_CASES,
    ids=[case.description for case in SQLSERVER_INTERMEDIATE_DAG_STRATEGY_TEST_CASES],
)
def test_given_intermediate_strategy_project_when_loading_twice_on_sqlserver_then_strategy_applies(
    tmp_path: Path,
    test_case: SqlServerIntermediateDagStrategyE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_load_dag_strategy")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_dag_strategy_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: amount\n"
                "        type: INTEGER\n"
            ),
            loader_py=test_case.loader_py,
        ),
    )
    (project_dir / "sqlbuild_project.toml").write_text(
        build_sqlserver_project_toml(
            project_name="source_loader_dag_strategy_behavior",
            schema_name=schema_name,
            config=config,
        ),
        encoding="utf-8",
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        first_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )
        second_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert first_result.returncode == test_case.expected_return_code, (
            first_result.stdout + first_result.stderr
        )
        assert second_result.returncode == test_case.expected_return_code, (
            second_result.stdout + second_result.stderr
        )
        intermediate_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT event_id, amount FROM "
                f"{relation_name(schema_name=schema_name, name='__loader__fetch_events')} "
                "ORDER BY event_id, amount"
            ),
        )
        terminal_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT event_id, amount FROM "
                f"{relation_name(schema_name=schema_name, name='raw_events')} "
                "ORDER BY event_id, amount"
            ),
        )
        assert stringify_warehouse_rows(intermediate_rows) == test_case.expected_intermediate_rows
        assert stringify_warehouse_rows(terminal_rows) == test_case.expected_terminal_rows
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerSnapshotE2ETestCase(
            description="executes snapshot scd2 matrix on SQL Server",
            expected_current_rows_after_initial_build=(("1", "10", "basic", "2026-01-01", None),),
            expected_current_rows_after_recovery=(
                ("1", "10", "basic", "2026-01-01", "2026-01-02"),
                ("1", "10", "pro", "2026-01-02", None),
            ),
            expected_historical_timestamp_rows=(
                ("1", "basic", "2026-01-01", "2026-01-03"),
                ("1", "pro", "2026-01-03", None),
                ("2", "trial", "2026-01-02", None),
            ),
            expected_historical_check_rows=(
                ("1", "active", "2026-01-01", "2026-01-03"),
                ("1", "paused", "2026-01-03", None),
                ("2", "active", "2026-01-01", "2026-01-02"),
            ),
            expected_failure_fragments=(
                "current_customer_snapshot",
                "delta audit for 'current_customer_snapshot' failed before target update",
            ),
        )
    ],
    ids=["executes snapshot scd2 matrix on SQL Server"],
)
def test_given_snapshot_project_when_building_on_sqlserver_then_scd2_history_is_valid(
    tmp_path: Path,
    test_case: SqlServerSnapshotE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_snapshot")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_snapshot_project",
        repo_files=adapt_sqlserver_project_files(
            build_real_warehouse_snapshot_project_files(
                project_toml=build_sqlserver_project_toml(
                    project_name="sqlserver_snapshot_project",
                    schema_name=schema_name,
                    config=config,
                ),
            )
        ),
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        initial_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--concurrency", "4"),
            project_dir=project_dir,
        )
        assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr
        assert_sqlserver_snapshot_matrix_rows(
            schema_name=schema_name,
            config=config,
            expected_current_rows=test_case.expected_current_rows_after_initial_build,
            expected_historical_timestamp_rows=test_case.expected_historical_timestamp_rows,
            expected_historical_check_rows=test_case.expected_historical_check_rows,
        )

        (project_dir / "models" / "current_customers.sql").write_text(
            adapt_sqlserver_sql(
                build_current_customers_model_sql(plan="blocked", updated_at="2026-01-02 00:00:00")
            ),
            encoding="utf-8",
        )
        failure_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "build",
                "--concurrency",
                "4",
                "--select",
                "+current_customer_snapshot",
            ),
            project_dir=project_dir,
        )
        assert failure_result.returncode == 1, failure_result.stdout + failure_result.stderr
        for fragment in test_case.expected_failure_fragments:
            assert fragment in failure_result.stdout + failure_result.stderr
        assert_current_sqlserver_snapshot_rows_from_case(
            schema_name=schema_name,
            config=config,
            expected_rows=test_case.expected_current_rows_after_initial_build,
        )

        (project_dir / "models" / "current_customers.sql").write_text(
            adapt_sqlserver_sql(
                build_current_customers_model_sql(plan="pro", updated_at="2026-01-02 00:00:00")
            ),
            encoding="utf-8",
        )
        recovery_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "build",
                "--concurrency",
                "4",
                "--select",
                "+current_customer_snapshot",
            ),
            project_dir=project_dir,
        )
        assert recovery_result.returncode == 0, recovery_result.stdout + recovery_result.stderr
        assert_current_sqlserver_snapshot_rows_from_case(
            schema_name=schema_name,
            config=config,
            expected_rows=test_case.expected_current_rows_after_recovery,
        )
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerSnapshotApplyE2ETestCase(
            description="applies existing-target snapshot changes on SQL Server",
            expected_current_check_rows=(
                ("1", "active", "0"),
                ("1", "paused", "1"),
                ("2", "active", "1"),
            ),
            expected_current_delete_rows=(
                ("1", "basic", "0"),
                ("1", "pro", "1"),
                ("2", "trial", "0"),
            ),
            expected_historical_timestamp_rows=(
                ("1", "basic", "2026-01-01", "2026-01-03"),
                ("1", "pro", "2026-01-03", None),
                ("2", "trial", "2026-01-01", "2026-01-04"),
            ),
            expected_historical_check_rows=(
                ("1", "active", "2026-01-01", "2026-01-03"),
                ("1", "paused", "2026-01-03", None),
                ("2", "active", "2026-01-01", "2026-01-02"),
            ),
        )
    ],
    ids=["applies existing-target snapshot changes on SQL Server"],
)
def test_given_existing_snapshot_targets_when_building_on_sqlserver_then_apply_sql_succeeds(
    tmp_path: Path,
    test_case: SqlServerSnapshotApplyE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_snapshot_apply")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_snapshot_apply_project",
        repo_files=adapt_sqlserver_project_files(
            build_real_warehouse_existing_snapshot_project_files(
                project_toml=build_sqlserver_project_toml(
                    project_name="sqlserver_snapshot_apply_project",
                    schema_name=schema_name,
                    config=config,
                ),
            )
        ),
    )
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        initial_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--concurrency", "4"),
            project_dir=project_dir,
        )
        assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

        (project_dir / "models" / "current_check_customers.sql").write_text(
            build_current_check_customers_model_sql(changed=True), encoding="utf-8"
        )
        (project_dir / "models" / "current_delete_customers.sql").write_text(
            adapt_sqlserver_sql(build_current_delete_customers_model_sql(changed=True)),
            encoding="utf-8",
        )
        (project_dir / "models" / "historical_timestamp_extracts.sql").write_text(
            adapt_sqlserver_sql(build_historical_timestamp_extracts_model_sql(changed=True)),
            encoding="utf-8",
        )
        (project_dir / "models" / "historical_check_daily.sql").write_text(
            adapt_sqlserver_sql(build_historical_check_daily_model_sql(changed=True)),
            encoding="utf-8",
        )

        apply_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--concurrency", "4"),
            project_dir=project_dir,
        )
        assert apply_result.returncode == 0, apply_result.stdout + apply_result.stderr
        assert_sqlserver_snapshot_apply_rows(
            schema_name=schema_name,
            config=config,
            expected_current_check_rows=test_case.expected_current_check_rows,
            expected_current_delete_rows=test_case.expected_current_delete_rows,
            expected_historical_timestamp_rows=test_case.expected_historical_timestamp_rows,
            expected_historical_check_rows=test_case.expected_historical_check_rows,
        )
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)
