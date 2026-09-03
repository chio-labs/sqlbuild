from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualBuildE2ETestCase,
    VirtualConcurrentMicrobatchE2ETestCase,
    VirtualCustomMaterializationE2ETestCase,
    VirtualWaffleShopE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    initialize_virtual_seeded_project,
    prepare_virtual_cursor_override_without_snapshot_project,
    prepare_virtual_seeded_incremental_project,
    rewrite_cursor_override_without_snapshot_model,
    rewrite_incremental_orders_model,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    prepare_waffle_shop,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentMicrobatchE2ETestCase(
            description="virtual concurrency stores state outside warehouse",
            expected_exit_code=0,
            expected_minimum_event_count=8,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_concurrent_microbatch_when_building_then_events_use_state_backend(
    test_case: VirtualConcurrentMicrobatchE2ETestCase, tmp_path: Path
) -> None:
    project_toml: str = build_virtual_plan_project_toml().replace(
        "virtual_environments = true\n",
        "virtual_environments = true\nconcurrency = 3\nmicrobatch_concurrency = true\n",
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_concurrent_microbatch",
        repo_files={
            "sqlbuild_project.toml": project_toml,
            "sources/raw.yml": """
sources:
  - name: raw_events
    schema: raw
    table: raw_events
""".strip()
            + "\n",
            "models/orders.sql": """
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  incremental_mode microbatch,
          microbatch_strategy watermark,
          cursor_watermark_mode all,
  cursor event_time,
  cursor_type timestamp,
  cursor_grain hour,
  microbatch_strategy watermark,
  cursor_watermark_mode all,
  cursor_inputs (
    raw_events (column event_time, roles [filter, watermark]),
  ),
  batch_size 1h,
  batch_concurrency 3,
);

SELECT id, event_time, payload
FROM __source("raw_events")
WHERE event_time >= __cursor_start()
  AND event_time < __cursor_end()
""".strip()
            + "\n",
        },
    )
    warehouse_path: Path = project_dir / "warehouse.duckdb"
    execute_duckdb(
        db_path=warehouse_path,
        sql=(
            "CREATE SCHEMA raw; "
            "CREATE TABLE raw.raw_events "
            "(id INTEGER, event_time TIMESTAMP, payload VARCHAR); "
            "INSERT INTO raw.raw_events VALUES "
            "(1, '2026-01-01 00:30:00', 'a'), "
            "(2, '2026-01-01 01:30:00', 'b'), "
            "(3, '2026-01-01 02:30:00', 'c')"
        ),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    execute_duckdb(
        db_path=warehouse_path,
        sql=(
            "INSERT INTO raw.raw_events VALUES "
            "(4, '2026-01-01 03:30:00', 'd'), "
            "(5, '2026-01-01 04:30:00', 'e'), "
            "(6, '2026-01-01 05:30:00', 'f')"
        ),
    )
    incremental_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert incremental_result.returncode == test_case.expected_exit_code, (
        incremental_result.stdout + incremental_result.stderr
    )

    assert query_duckdb(
        db_path=warehouse_path,
        sql="SELECT id, payload FROM dev__dev.orders ORDER BY id",
    ) == [(1, "a"), (2, "b"), (3, "c"), (4, "d"), (5, "e"), (6, "f")]
    virtual_history: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT scope_kind, fingerprint_status, COUNT(*) "
            "FROM sqlbuild_state.microbatch_events "
            "GROUP BY scope_kind, fingerprint_status"
        ),
    )
    assert len(virtual_history) == 1
    assert virtual_history[0][:2] == ("virtual_physical", "known")
    assert int(str(virtual_history[0][2])) >= test_case.expected_minimum_event_count
    assert query_duckdb(
        db_path=warehouse_path,
        sql=(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = '_sqlbuild_microbatches'"
        ),
    ) == [(0,)]

    version_hash: str = str(
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_node_refs "
                "WHERE virtual_environment_name = 'dev' "
                "AND node_type = 'model' AND node_name = 'orders'"
            ),
        )[0][0]
    )
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=("SELECT DISTINCT virtual_model_version_hash FROM sqlbuild_state.microbatch_events"),
    ) == [(version_hash,)]
    scope_key: str = str(
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql="SELECT DISTINCT scope_key FROM sqlbuild_state.microbatch_events",
        )[0][0]
    )
    warehouse_realm: str = scope_key.split(":")[2]
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
            f"('model_version:{warehouse_realm}:orders:{version_hash}', 'other-build', "
            "CURRENT_TIMESTAMP + INTERVAL 1 HOUR, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )
    execute_duckdb(
        db_path=warehouse_path,
        sql="INSERT INTO raw.raw_events VALUES (7, '2026-01-01 06:30:00', 'g')",
    )

    conflicted_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert conflicted_result.returncode != 0
    assert "physical version is already being mutated" in (
        conflicted_result.stdout + conflicted_result.stderr
    )
    assert query_duckdb(
        db_path=warehouse_path,
        sql="SELECT COUNT(*) FROM dev__dev.orders",
    ) == [(6,)]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentMicrobatchE2ETestCase(
            description="failed first virtual microbatch can retry provisional physical mapping",
            expected_exit_code=0,
            expected_minimum_event_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failed_first_virtual_microbatch_when_retried_then_provisional_mapping_is_reused(
    test_case: VirtualConcurrentMicrobatchE2ETestCase, tmp_path: Path
) -> None:
    project_toml: str = build_virtual_plan_project_toml().replace(
        "virtual_environments = true\n",
        "virtual_environments = true\nconcurrency = 2\nmicrobatch_concurrency = true\n",
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_failed_first_microbatch",
        repo_files={
            "sqlbuild_project.toml": project_toml,
            "sources/raw.yml": (
                "sources:\n  - name: raw_events\n    schema: raw\n    table: raw_events\n"
            ),
            "models/orders.sql": (
                "MODEL (\n"
                "  materialized incremental,\n"
                "  incremental_strategy delete_insert,\n"
                "  incremental_mode microbatch,\n"
                "  microbatch_strategy watermark,\n"
                "  cursor_watermark_mode all,\n"
                "  cursor event_time,\n"
                "  cursor_type timestamp,\n"
                "  cursor_grain hour,\n"
                "  cursor_inputs (raw_events (column event_time, roles [filter, watermark]),),\n"
                "  batch_size 1h,\n"
                "  batch_concurrency 2,\n"
                ");\n"
                "SELECT id, event_time, CAST(payload AS INTEGER) AS value\n"
                'FROM __source("raw_events")\n'
                "WHERE event_time >= __cursor_start() AND event_time < __cursor_end()\n"
            ),
        },
    )
    warehouse_path: Path = project_dir / "warehouse.duckdb"
    execute_duckdb(
        db_path=warehouse_path,
        sql=(
            "CREATE SCHEMA raw; "
            "CREATE TABLE raw.raw_events "
            "(id INTEGER, event_time TIMESTAMP, payload VARCHAR); "
            "INSERT INTO raw.raw_events VALUES (1, '2026-01-01 00:30:00', 'bad')"
        ),
    )
    initialized: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert initialized.returncode == test_case.expected_exit_code, (
        initialized.stdout + initialized.stderr
    )
    failed: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert failed.returncode != test_case.expected_exit_code
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT COUNT(*) FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'model' AND artifact_name = 'orders'"
        ),
    ) == [(1,)]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=("SELECT COUNT(*) FROM sqlbuild_state.locks WHERE lock_key LIKE 'model_version:%'"),
    ) == [(0,)]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT COUNT(*) FROM sqlbuild_state.microbatch_events "
            "WHERE record_type = 'partition_completion' AND rows_affected > 0"
        ),
    ) == [(0,)]

    execute_duckdb(
        db_path=warehouse_path,
        sql="UPDATE raw.raw_events SET payload = '1'",
    )
    retried: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert retried.returncode == test_case.expected_exit_code, retried.stdout + retried.stderr
    assert query_duckdb(
        db_path=warehouse_path,
        sql="SELECT id, value FROM dev__dev.orders",
    ) == [(1, 1)]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildE2ETestCase(
            description="delete-insert incremental seeds new physical version from prior version",
            expected_build_fragments=(),
            expected_plan_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.orders ORDER BY id",
                    ((1, 10), (2, 21), (3, 31)),
                ),
            ),
            expected_ref_rows=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_incremental_change_when_building_then_it_seeds_new_physical_version(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_seeded_incremental_project(
        tmp_path=tmp_path,
        project_name="virtual_seeded_delete_insert",
        incremental_strategy="delete_insert",
        replay_on_change="bounded-7d",
    )
    initialize_virtual_seeded_project(project_dir=project_dir)

    rewrite_incremental_orders_model(
        project_dir=project_dir,
        incremental_strategy="delete_insert",
        replay_on_change="bounded-7d",
        amount_expression="amount_cents + 1",
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="INSERT INTO raw.raw_orders VALUES (3, '2026-01-03 00:00:00', 30)",
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

    assert build_result.returncode == 0, build_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    ancestry_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT parent_model_name, seed_strategy "
            "FROM sqlbuild_state.physical_relation_ancestry "
            "WHERE model_name = 'orders'"
        ),
    )
    assert ancestry_rows == [("orders", "copy")]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildE2ETestCase(
            description="explicit cursor overrides work without target or upstream snapshots",
            expected_build_fragments=(),
            expected_plan_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.orders ORDER BY id",
                    ((1, 10), (2, 21), (3, 31)),
                ),
            ),
            expected_ref_rows=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_incremental_without_cursor_snapshot_when_building_then_cli_bounds_apply(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_cursor_override_without_snapshot_project(
        tmp_path=tmp_path,
        project_name="virtual_cursor_override_without_snapshot",
    )
    initialize_virtual_seeded_project(project_dir=project_dir)

    rewrite_cursor_override_without_snapshot_model(
        project_dir=project_dir,
        amount_expression="amount_cents + 1",
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "DELETE FROM raw.raw_orders WHERE id = 1; "
            "INSERT INTO raw.raw_orders VALUES (3, '2026-01-03 00:00:00', 30)"
        ),
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

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCustomMaterializationE2ETestCase(
            description="custom materialization prepare_version seeds changed physical target",
            expected_query_results=(
                (
                    "SELECT id, amount_cents, version_marker FROM dev__dev.orders ORDER BY id",
                    (
                        (1, 10, "prepared"),
                        (2, 21, "materialized"),
                        (3, 30, "materialized"),
                    ),
                ),
            ),
            expected_ancestry_rows=(("custom_prepare_version",),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_custom_materialization_when_model_changes_then_prepare_version_seeds_target(
    test_case: VirtualCustomMaterializationE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_custom_materialization",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "materializations/merge_by_id.py": """
from sqlbuild.executor.custom.models import (
    MaterializationContext,
    MaterializationResult,
    PrepareVersionContext,
)


def prepare_version(ctx: PrepareVersionContext) -> None:
    ctx.execute_sql(
        f"CREATE TABLE {ctx.destination} AS "
        f"SELECT id, amount_cents, 'prepared' AS version_marker FROM {ctx.origin_relation}"
    )


def materialize(ctx: MaterializationContext) -> MaterializationResult:
    incoming = (
        "SELECT id, amount_cents, 'materialized' AS version_marker "
        f"FROM ({ctx.sql}) AS model_sql"
    )
    exists = ctx.adapter.relation_exists(
        connection=ctx.connection,
        database=ctx.destination_database,
        schema=ctx.destination_schema,
        name=ctx.destination_name,
    )
    if not exists:
        ctx.execute_sql(f"CREATE TABLE {ctx.destination} AS {incoming}")
    else:
        ctx.execute_sql(
            f"DELETE FROM {ctx.destination} WHERE id IN "
            f"(SELECT id FROM ({ctx.sql}) AS model_sql)"
        )
        ctx.execute_sql(f"INSERT INTO {ctx.destination} {incoming}")
    return MaterializationResult(relation=ctx.destination)
""",
            "models/orders.sql": """
MODEL (materialized merge_by_id);

SELECT 1 AS id, 10 AS amount_cents
UNION ALL SELECT 2 AS id, 20 AS amount_cents
""",
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert first_build_result.returncode == 0, first_build_result.stderr

    (project_dir / "models" / "orders.sql").write_text(
        """
MODEL (materialized merge_by_id);

SELECT 2 AS id, 21 AS amount_cents
UNION ALL SELECT 3 AS id, 30 AS amount_cents
""",
        encoding="utf-8",
    )

    second_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert second_build_result.returncode == 0, second_build_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT seed_strategy FROM sqlbuild_state.physical_relation_ancestry "
            "WHERE model_name = 'orders'"
        ),
    ) == list(test_case.expected_ancestry_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualWaffleShopE2ETestCase(
            description="full waffle shop fixture builds in virtual mode",
            expected_view_names=(
                "customer_status_snapshot",
                "daily_activity_rollup",
                "daily_order_partitioned",
                "daily_revenue",
                "dim_customers",
                "fact_orders",
                "hourly_activity_with_daily_context",
                "hourly_order_activity",
                "order_status_index",
                "stg_customers",
                "stg_orders",
                "stg_payments",
            ),
            expected_function_names=(
                "customer_orders",
                "is_completed_order",
                "is_completed_order_py",
            ),
            expected_query_results=(
                (
                    "SELECT order_id, customer_id, waffle_name, order_status "
                    "FROM dev__dev.fact_orders ORDER BY order_id LIMIT 3",
                    (
                        (1, 1, "Classic Belgian", "completed"),
                        (2, 1, "Cheddar Herb", "completed"),
                        (3, 2, "Chicken and Waffle", "completed"),
                    ),
                ),
                (
                    "SELECT order_id, is_completed_order_py FROM dev__dev.fact_orders "
                    "WHERE order_id IN (1, 10) ORDER BY order_id",
                    ((1, True), (10, False)),
                ),
                (
                    "SELECT order_id, waffle_name, line_total_cents, order_status, "
                    "is_completed_order FROM dev__dev.customer_orders(1) ORDER BY order_id",
                    (
                        (1, "Classic Belgian", 1700, "completed", True),
                        (2, "Cheddar Herb", 1050, "completed", True),
                        (8, "Liege", 950, "completed", True),
                    ),
                ),
                (
                    "SELECT CAST(order_date AS VARCHAR), order_count, waffles_ordered, "
                    "unique_customers FROM dev__dev.daily_order_partitioned ORDER BY order_date",
                    (
                        ("2026-04-01", 3, 6, 2),
                        ("2026-04-02", 3, 3, 2),
                        ("2026-04-03", 2, 3, 2),
                        ("2026-04-04", 2, 6, 2),
                    ),
                ),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_waffle_shop_project_when_virtual_building_then_vde_outputs_are_queryable(
    test_case: VirtualWaffleShopE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    (project_dir / "sqlbuild_project.toml").write_text(
        """
name = "waffle_shop"
adapter = "duckdb"
default_target = "dev"

[settings]
virtual_environments = true
default_audit_severity = "warn"

[connection]
database = "waffle_shop.duckdb"

[defaults]
materialized = "table"

[path_defaults.staging]
materialized = "view"

[targets.dev]
schema = "dev"
defer_sources_to = "dev"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
        encoding="utf-8",
    )
    db_path: Path = project_dir / "waffle_shop.duckdb"
    execution_json_path: Path = project_dir / "target" / "virtual-build.json"

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--json-output", str(execution_json_path)),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    view_name: str
    for view_name in test_case.expected_view_names:
        assert table_exists(db_path=db_path, schema="dev__dev", table_name=view_name)

    payload: dict[str, object] = json.loads(execution_json_path.read_text(encoding="utf-8"))
    assets: list[dict[str, object]] = list(payload["assets"])  # type: ignore[arg-type]
    assets_by_name: dict[str, dict[str, object]] = {str(asset["name"]): asset for asset in assets}
    assert len(assets_by_name) == len(assets)
    function_name: str
    for function_name in test_case.expected_function_names:
        assert assets_by_name[function_name]["kind"] in {"udf", "table_fn"}
        assert assets_by_name[function_name]["status"] == "success"

    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=db_path, sql=query_sql) == list(expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildE2ETestCase(
            description="append bounded incremental seeds only rows before replay window",
            expected_build_fragments=(),
            expected_plan_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.orders ORDER BY id",
                    ((1, 10), (2, 21), (3, 31)),
                ),
            ),
            expected_ref_rows=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_append_bounded_change_when_building_then_seed_excludes_replay_window(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_seeded_incremental_project(
        tmp_path=tmp_path,
        project_name="virtual_seeded_append",
        incremental_strategy="append",
        replay_on_change="bounded-7d",
    )
    initialize_virtual_seeded_project(project_dir=project_dir)

    rewrite_incremental_orders_model(
        project_dir=project_dir,
        incremental_strategy="append",
        replay_on_change="bounded-7d",
        amount_expression="amount_cents + 1",
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="INSERT INTO raw.raw_orders VALUES (3, '2026-01-03 00:00:00', 30)",
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

    assert build_result.returncode == 0, build_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    ancestry_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT parent_model_name, seed_strategy "
            "FROM sqlbuild_state.physical_relation_ancestry "
            "WHERE model_name = 'orders'"
        ),
    )
    assert ancestry_rows == [("orders", "bounded_append_copy")]
