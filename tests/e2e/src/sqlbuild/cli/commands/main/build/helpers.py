from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DeferCloneBuildE2ETestCase,
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


def capped_microbatch_project_files(
    *, limit_action: str, project_limit: str = ""
) -> dict[str, str]:
    """Build a direct DuckDB project with one capped producer and consumer."""

    return {
        "sqlbuild_project.toml": dedent(
            f"""
            name = "capped_microbatch"
            adapter = "duckdb"

            [connection]
            database = "regression.duckdb"
            {project_limit}
            """
        ).strip()
        + "\n",
        "sources/raw.yml": dedent(
            """
            sources:
              - name: raw_events
                schema: main
                table: raw_events
            """
        ).strip()
        + "\n",
        "models/capped_events.sql": dedent(
            f"""
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
              microbatch_strategy watermark,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain day,
              cursor_start '2026-01-01',
              cursor_end '2026-01-06',
              cursor_watermark_mode all,
              cursor_inputs (
                raw_events (column event_time, roles [filter, watermark]),
              ),
              batch_size 1d,
              lookback 1d,
              microbatch_limit (
                max_batches 3,
                action {limit_action},
              ),
            );
            SELECT id, event_time
            FROM __source("raw_events")
            """
        ).strip()
        + "\n",
        "models/downstream_events.sql": dedent(
            """
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
              microbatch_strategy watermark,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain day,
              cursor_start '2026-01-01',
              cursor_watermark_mode all,
              cursor_inputs (
                capped_events (column event_time, roles [filter, watermark]),
              ),
              batch_size 1d,
              lookback 1d,
            );
            SELECT id, event_time
            FROM __ref("capped_events")
            """
        ).strip()
        + "\n",
    }


def prepare_defer_clone_project(
    *,
    tmp_path: Path,
    project_name: str,
    upstream_sql: str,
    downstream_sql: str,
) -> Path:
    """Write a direct-mode project with clone policies for defer-clone E2Es."""

    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": dedent(
                f"""
                name = "{project_name}"
                adapter = "duckdb"
                default_target = "dev"

                [connection]
                database = "warehouse.duckdb"

                [targets.prod]
                schema = "prod"

                [targets.prod.clone]
                allow_as_clone_origin = true

                [targets.dev]
                schema = "dev"

                [targets.dev.clone]
                allow_as_clone_destination = true
                """
            ).strip()
            + "\n",
            "models/upstream.sql": upstream_sql,
            "models/downstream.sql": downstream_sql,
        },
    )


def build_virtual_wide_dag_repo_files(*, model_count: int) -> dict[str, str]:
    repo_files: dict[str, str] = {
        "sqlbuild_project.toml": build_virtual_plan_project_toml(),
    }
    for index in range(1, model_count + 1):
        model_name: str = f"model_{index:02d}"
        repo_files[f"models/{model_name}.sql"] = (
            f"MODEL (materialized table);\n\nSELECT {index} AS id, '{model_name}' AS model_name\n"
        )
    return repo_files


def table_upstream_model_sql(*, amount: int = 100) -> str:
    return f"MODEL (materialized table);\n\nSELECT id, {amount} AS amount FROM main.raw_orders\n"


def incremental_upstream_model_sql() -> str:
    return (
        dedent(
            """
        MODEL (
          materialized incremental,
          incremental_strategy append,
          cursor event_time,
          cursor_type timestamp,
          cursor_grain second,
        );

        SELECT id, amount, event_time FROM main.raw_orders
        """
        ).strip()
        + "\n"
    )


def downstream_model_sql() -> str:
    return (
        "MODEL (materialized table);\n\n"
        'SELECT id, amount AS downstream_amount FROM __ref("upstream")\n'
    )


def raw_orders_setup_sql(*, rows_sql: str) -> str:
    return (
        "CREATE TABLE main.raw_orders (id INTEGER, amount INTEGER, event_time TIMESTAMP);\n"
        f"INSERT INTO main.raw_orders VALUES {rows_sql};\n"
    )


def replace_raw_orders_versions(*, db_path: Path, versions: tuple[int, ...]) -> None:
    values_sql: str = ", ".join(
        f"({index + 1}, {version})" for index, version in enumerate(versions)
    )
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE raw_orders (id INTEGER, data_version INTEGER);\n"
            f"INSERT INTO raw_orders VALUES {values_sql};\n"
        ),
    )


def run_successful_sqb_build(*, project_dir: Path, command: tuple[str, ...]) -> None:
    result: subprocess.CompletedProcess[str] = run_sqb(command=command, project_dir=project_dir)
    assert result.returncode == 0, result.stdout + result.stderr


def assert_defer_clone_build_case(*, tmp_path: Path, test_case: DeferCloneBuildE2ETestCase) -> None:
    """Run and assert one direct-mode defer-clone E2E case."""

    project_dir: Path = prepare_defer_clone_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        upstream_sql=test_case.initial_upstream_sql,
        downstream_sql=test_case.downstream_sql,
    )
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.prod_build_command,
        project_dir=project_dir,
    )
    assert prod_result.returncode == 0, prod_result.stderr or prod_result.stdout
    project_config_path: Path = project_dir / "sqlbuild_project.toml"
    project_config_path.write_text(
        project_config_path.read_text(encoding="utf-8").replace(
            '[targets.prod]\nschema = "prod"',
            '[targets.prod]\nschema = "prod"\n\n[targets.prod.connection]\n'
            'database = "${ENV:SQLBUILD_TEST_UNUSED_DEFER_ORIGIN_DATABASE}"',
        ),
        encoding="utf-8",
    )
    (project_dir / "models" / "upstream.sql").write_text(
        test_case.changed_upstream_sql,
        encoding="utf-8",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.dev_build_command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_stdout_fragments:
        assert unexpected_fragment not in result.stdout
    db_path: Path = project_dir / "warehouse.duckdb"
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT id, label FROM prod.upstream ORDER BY id",
    ) == list(test_case.expected_prod_upstream_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT id, label FROM dev.upstream ORDER BY id",
    ) == list(test_case.expected_dev_upstream_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT id, label FROM dev.downstream ORDER BY id",
    ) == list(test_case.expected_dev_downstream_rows)
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_type, node_name FROM dev._sqlbuild_fingerprints "
            "WHERE node_type = 'model' ORDER BY node_name"
        ),
    ) == list(test_case.expected_fingerprint_rows)


def _apply_command_target(*, project_dir: Path, command: tuple[str, ...]) -> tuple[str, ...]:
    command_with_sentinel: tuple[str, ...] = (*command, "--target")
    target_index: int = command_with_sentinel.index("--target")
    target_names: tuple[str, ...] = command[target_index + 1 : target_index + 2]
    for target_name in target_names:
        (project_dir / "sqlbuild_local.toml").write_text(
            f'target = "{target_name}"\n', encoding="utf-8"
        )
    return (*command[:target_index], *command[target_index + 2 * len(target_names) :])


def _apply_optional_dev_setup_sql(*, project_dir: Path, sql: str | None) -> None:
    for setup_sql in (sql,) * int(sql is not None):
        assert setup_sql is not None
        execute_duckdb(db_path=project_dir / "warehouse.duckdb", sql=setup_sql)


def prepare_virtual_seeded_incremental_project(
    *,
    tmp_path: Path,
    project_name: str,
    incremental_strategy: str,
    replay_on_change: str,
) -> Path:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                """
            ).strip()
            + "\n",
            "models/orders.sql": incremental_orders_model_sql(
                incremental_strategy=incremental_strategy,
                replay_on_change=replay_on_change,
                amount_expression="amount_cents + 0",
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (
              id INTEGER,
              ordered_at TIMESTAMP,
              amount_cents INTEGER
            );
            INSERT INTO raw.raw_orders VALUES
              (1, '2026-01-01 00:00:00', 10),
              (2, '2026-01-02 00:00:00', 20);
            """
        ).strip(),
    )
    return project_dir


def build_virtual_seed_lifecycle_repo_files(*, amount_cents: int) -> dict[str, str]:
    return build_virtual_plan_repo_files(
        stg_orders_sql='SELECT id, amount_cents FROM __seed("order_amounts")'
    ) | {
        "seeds/orders.yml": (
            "seeds:\n"
            "  - name: order_amounts\n"
            "    path: order_amounts.csv\n"
            "    columns:\n"
            "      - name: id\n"
            "        type: integer\n"
            "      - name: amount_cents\n"
            "        type: integer\n"
        ),
        "seeds/order_amounts.csv": f"id,amount_cents\n1,{amount_cents}\n",
    }


def build_virtual_multi_seed_lifecycle_repo_files(
    *, amount_cents: int, multiplier: int
) -> dict[str, str]:
    return build_virtual_plan_repo_files(
        stg_orders_sql=(
            "SELECT a.id, a.amount_cents * m.multiplier AS amount_cents "
            'FROM __seed("order_amounts") a '
            'JOIN __seed("amount_multipliers") m USING (id)'
        )
    ) | {
        "seeds/orders.yml": (
            "seeds:\n"
            "  - name: order_amounts\n"
            "    path: order_amounts.csv\n"
            "    columns:\n"
            "      - name: id\n"
            "        type: integer\n"
            "      - name: amount_cents\n"
            "        type: integer\n"
            "  - name: amount_multipliers\n"
            "    path: amount_multipliers.csv\n"
            "    columns:\n"
            "      - name: id\n"
            "        type: integer\n"
            "      - name: multiplier\n"
            "        type: integer\n"
        ),
        "seeds/order_amounts.csv": f"id,amount_cents\n1,{amount_cents}\n",
        "seeds/amount_multipliers.csv": f"id,multiplier\n1,{multiplier}\n",
    }


def prepare_build_test_audit_flag_project(*, tmp_path: Path, project_name: str) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": dedent(
                f"""
                name = "{project_name}"
                adapter = "duckdb"

                [connection]
                database = "warehouse.duckdb"
                """
            ).strip()
            + "\n",
            "models/orders.sql": dedent(
                """
                MODEL (
                  materialized table,
                  columns (order_id (audits [not_null])),
                );

                SELECT 1 AS order_id
                """
            ).strip()
            + "\n",
            "tests/unit/test_orders.sql": dedent(
                """
                TEST();

                WITH
                __ref__orders AS (SELECT 1 AS order_id),
                __expected__orders AS (SELECT 1 AS order_id)
                SELECT 1
                """
            ).strip()
            + "\n",
        },
    )


def build_freshness_error_branch_source_yml(
    *,
    order_id: int,
    customer_id: int,
    order_freshness_query: str,
    customer_freshness_query: str,
) -> str:
    return (
        dedent(
            f"""
        sources:
          - name: raw_orders
            expression: SELECT {order_id} AS order_id
            freshness:
              strategy: sql
              type: timestamp
              query: {order_freshness_query}
              age_policy:
                error_after: 1h
          - name: raw_customers
            expression: SELECT {customer_id} AS customer_id
            freshness:
              strategy: sql
              type: timestamp
              query: {customer_freshness_query}
              age_policy:
                error_after: 1h
        """
        ).strip()
        + "\n"
    )


def prepare_virtual_cursor_override_without_snapshot_project(
    *,
    tmp_path: Path,
    project_name: str,
) -> Path:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                """
            ).strip()
            + "\n",
            "models/orders.sql": _cursor_override_without_snapshot_model_sql(
                amount_expression="amount_cents + 0"
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (
              id INTEGER,
              ordered_at TIMESTAMP,
              amount_cents INTEGER
            );
            INSERT INTO raw.raw_orders VALUES
              (1, '2026-01-01 00:00:00', 10),
              (2, '2026-01-02 00:00:00', 20);
            """
        ).strip(),
    )
    return project_dir


def rewrite_cursor_override_without_snapshot_model(
    *, project_dir: Path, amount_expression: str
) -> None:
    (project_dir / "models" / "orders.sql").write_text(
        _cursor_override_without_snapshot_model_sql(amount_expression=amount_expression),
        encoding="utf-8",
    )


def initialize_virtual_seeded_project(*, project_dir: Path) -> None:
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


def rewrite_incremental_orders_model(
    *,
    project_dir: Path,
    incremental_strategy: str,
    replay_on_change: str,
    amount_expression: str,
) -> None:
    (project_dir / "models" / "orders.sql").write_text(
        incremental_orders_model_sql(
            incremental_strategy=incremental_strategy,
            replay_on_change=replay_on_change,
            amount_expression=amount_expression,
        ),
        encoding="utf-8",
    )


def count_virtual_physical_versions(*, project_dir: Path, schema: str = "dev__sqb_physical") -> int:
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT COUNT(*) FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' AND table_name LIKE '%__v_%'"
        ),
    )
    return int(rows[0][0])


def incremental_orders_model_sql(
    *, incremental_strategy: str, replay_on_change: str, amount_expression: str
) -> str:
    return (
        dedent(
            f"""
            MODEL (
              materialized incremental,
              incremental_strategy {incremental_strategy},
              cursor ordered_at,
              cursor_type timestamp,
              cursor_grain day,
              replay_on_change {replay_on_change}
            );

            SELECT id, ordered_at, {amount_expression} AS amount_cents
            FROM __source("raw_orders")
            """
        ).strip()
        + "\n"
    )


def _cursor_override_without_snapshot_model_sql(*, amount_expression: str) -> str:
    return (
        dedent(
            f"""
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              cursor ordered_at,
              cursor_type timestamp,
              cursor_grain day,
              cursor_inputs (raw_orders ordered_at,),
              replay_on_change bounded-7d
            );

            SELECT id, ordered_at, {amount_expression} AS amount_cents
            FROM __source("raw_orders")
            """
        ).strip()
        + "\n"
    )


def replay_microbatch_model_sql(*, value_expression: str, replay_policy: str = "bounded-2h") -> str:
    """Build a replay-on-change microbatch model used by lifecycle E2E tests."""

    return (
        dedent(
            f"""
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
              microbatch_strategy watermark,
              cursor_watermark_mode all,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain hour,
              cursor_inputs (
                raw_events (column event_time, roles [filter, watermark]),
              ),
              batch_size 1h,
              batch_concurrency 2,
              replay_on_change {replay_policy},
            );

            SELECT id, event_time, {value_expression} AS value
            FROM __source("raw_events")
            WHERE event_time >= __cursor_start()
              AND event_time < __cursor_end()
            """
        ).strip()
        + "\n"
    )


def direct_microbatch_project_toml(
    *, project_name: str, database_name: str, settings_toml: str
) -> str:
    """Build a direct DuckDB project config for microbatch lifecycle E2Es."""

    return (
        f'name = "{project_name}"\n'
        'adapter = "duckdb"\n\n'
        "[connection]\n"
        f'database = "{database_name}"\n'
        f"{settings_toml}"
    )


def raw_events_source_yml() -> str:
    """Return the canonical raw-events source declaration."""

    return "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"


def timestamp_microbatch_model_sql(
    *,
    value_expression: str,
    batch_concurrency: int,
    replay_policy: str,
    extra_config: str = "",
) -> str:
    """Build a timestamp delete/insert microbatch model for lifecycle E2Es."""

    return (
        dedent(
            f"""
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
              microbatch_strategy watermark,
              cursor_watermark_mode all,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain hour,
              cursor_inputs (
                raw_events (column event_time, roles [filter, watermark]),
              ),
              batch_size 1h,
              batch_concurrency {batch_concurrency},
              replay_on_change {replay_policy},
              {extra_config}
            );

            SELECT id, event_time, {value_expression} AS value
            FROM __source("raw_events")
            WHERE event_time >= __cursor_start()
              AND event_time < __cursor_end()
            """
        ).strip()
        + "\n"
    )


def prepare_replay_microbatch_project(
    *, tmp_path: Path, project_name: str, database_name: str, replay_policy: str
) -> tuple[Path, Path]:
    """Prepare a direct concurrent replay lifecycle project."""

    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": direct_microbatch_project_toml(
                project_name=project_name,
                database_name=database_name,
                settings_toml=("\n[settings]\nconcurrency = 3\nmicrobatch_concurrency = true\n"),
            ),
            "sources/raw.yml": raw_events_source_yml(),
            "models/orders.sql": timestamp_microbatch_model_sql(
                value_expression="CAST(payload AS INTEGER)",
                batch_concurrency=3,
                replay_policy=replay_policy,
            ),
        },
    )
    return project_dir, project_dir / database_name


def prepare_virtual_microbatch_lifecycle_project(
    *,
    tmp_path: Path,
    project_name: str,
    model_sql: str,
    unaccounted_policy: str = "synthesize",
    enable_janitor: bool = False,
) -> tuple[Path, Path, Path]:
    """Prepare a virtual concurrent microbatch lifecycle project."""

    project_toml: str = build_virtual_plan_project_toml().replace(
        "virtual_environments = true\n",
        (
            "virtual_environments = true\n"
            "concurrency = 3\n"
            "microbatch_concurrency = true\n"
            f'microbatch_unaccounted_partition_policy = "{unaccounted_policy}"\n'
        ),
    )
    project_toml += {
        False: "",
        True: ("\n[janitor]\nenabled = true\nretention_days = 0\ndelete_tracked_only = false\n"),
    }[enable_janitor]
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": project_toml,
            "sources/raw.yml": (
                "sources:\n  - name: raw_events\n    schema: raw\n    table: raw_events\n"
            ),
            "models/orders.sql": model_sql,
        },
    )
    warehouse_path: Path = project_dir / "warehouse.duckdb"
    state_path: Path = project_dir / "state.duckdb"
    execute_duckdb(
        db_path=warehouse_path,
        sql=(
            "CREATE SCHEMA raw; "
            "CREATE TABLE raw.raw_events "
            "(id INTEGER, event_time TIMESTAMP, payload VARCHAR); "
            "INSERT INTO raw.raw_events VALUES "
            "(1, '2026-01-01 00:30:00', '1'), "
            "(2, '2026-01-01 01:30:00', '2'), "
            "(3, '2026-01-01 02:30:00', '3'), "
            "(4, '2026-01-01 03:30:00', '4')"
        ),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr
    return project_dir, warehouse_path, state_path


def physical_orders_relation(*, state_path: Path) -> tuple[str, str]:
    """Return the latest registered physical orders relation."""

    schema_name, relation_name = query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT schema_name, relation_name "
            "FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'model' AND artifact_name = 'orders' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
    )[0]
    return str(schema_name), str(relation_name)
