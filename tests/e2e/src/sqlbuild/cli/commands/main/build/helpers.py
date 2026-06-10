from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


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
              cursor_inputs (),
              replay_on_change bounded-7d
            );

            SELECT id, ordered_at, {amount_expression} AS amount_cents
            FROM __source("raw_orders")
            """
        ).strip()
        + "\n"
    )


def prepare_direct_changes_only_two_model_project(
    *, tmp_path: Path, project_name: str, amount_cents: int
) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/stg_orders.sql": direct_changes_only_stg_orders_sql(amount_cents=amount_cents),
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT\n"
                "  order_id,\n"
                "  amount_cents,\n"
                "  amount_cents / 100.0 AS amount_dollars\n"
                'FROM __ref("stg_orders")\n'
            ),
        },
    )


def prepare_direct_reuse_from_project(*, tmp_path: Path, project_name: str) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{project_name}"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.prod]\n"
                'schema = "prod"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'reuse_from = "prod"\n'
                "reuse_hard_copy = true\n"
            ),
            "models/orders.sql": (
                "MODEL (materialized table);\n\nSELECT random() AS reuse_marker\n"
            ),
        },
    )


def prepare_direct_snapshot_reuse_from_project(*, tmp_path: Path, project_name: str) -> Path:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{project_name}"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.prod]\n"
                'schema = "prod"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'reuse_from = "prod"\n'
                "reuse_hard_copy = true\n"
            ),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_accounts
                    schema: raw
                    table: raw_accounts
                """
            ).strip()
            + "\n",
            "models/account_snapshot.sql": dedent(
                """
                MODEL (
                  materialized snapshot,
                  unique_key [account_id],
                  snapshot_strategy timestamp,
                  updated_at updated_at
                );

                SELECT account_id, plan, updated_at FROM __source("raw_accounts")
                """
            ).strip()
            + "\n",
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_accounts AS
            SELECT 1 AS account_id, 'basic' AS plan, TIMESTAMP '2024-01-01 00:00:00' AS updated_at;
            """
        ).strip(),
    )
    return project_dir


def prepare_direct_custom_reuse_from_project(*, tmp_path: Path, project_name: str) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{project_name}"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.prod]\n"
                'schema = "prod"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'reuse_from = "prod"\n'
                "reuse_hard_copy = true\n"
            ),
            "materializations/merge_by_id.py": dedent(
                """
                from sqlbuild.executor.custom.models import (
                    MaterializationContext,
                    MaterializationResult,
                    PrepareVersionContext,
                )


                def prepare_version(ctx: PrepareVersionContext) -> None:
                    ctx.execute_sql(f"DROP TABLE IF EXISTS {ctx.destination}")
                    ctx.execute_sql(
                        f"CREATE TABLE {ctx.destination} AS "
                        "SELECT id, amount_cents, 'prepared_from_prod' AS prepare_marker, "
                        f"materialize_marker FROM {ctx.origin_relation}"
                    )


                def materialize(ctx: MaterializationContext) -> MaterializationResult:
                    exists = ctx.adapter.relation_exists(
                        ctx.connection,
                        database=ctx.destination_database,
                        schema=ctx.destination_schema,
                        name=ctx.destination_name,
                    )
                    if not exists:
                        incoming = (
                            "SELECT id, amount_cents, 'fresh' AS prepare_marker, "
                            f"'finalized' AS materialize_marker FROM ({ctx.sql}) AS model_sql"
                        )
                        ctx.execute_sql(f"CREATE TABLE {ctx.destination} AS {incoming}")
                    else:
                        incoming = (
                            "SELECT model_sql.id, model_sql.amount_cents, "
                            "COALESCE(existing.prepare_marker, 'fresh') AS prepare_marker, "
                            "'finalized' AS materialize_marker "
                            f"FROM ({ctx.sql}) AS model_sql "
                            f"LEFT JOIN {ctx.destination} AS existing USING (id)"
                        )
                        ctx.execute_sql(
                            f"CREATE OR REPLACE TEMP TABLE sqb_custom_next AS {incoming}"
                        )
                        ctx.execute_sql(f"DELETE FROM {ctx.destination}")
                        ctx.execute_sql(
                            f"INSERT INTO {ctx.destination} SELECT * FROM sqb_custom_next"
                        )
                    return MaterializationResult(relation=ctx.destination)
                """
            ).strip()
            + "\n",
            "models/orders.sql": dedent(
                """
                MODEL (materialized merge_by_id);

                SELECT 1 AS id, 10 AS amount_cents
                UNION ALL SELECT 2 AS id, 20 AS amount_cents
                """
            ).strip()
            + "\n",
        },
    )


def prepare_direct_reuse_from_multi_schema_project(*, tmp_path: Path, project_name: str) -> Path:
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

                [path_defaults.staging]
                schema = "prod_staging"
                materialized = "table"

                [path_defaults.intermediate]
                schema = "prod_intermediate"
                materialized = "table"

                [path_defaults.marts]
                schema = "prod_marts"
                materialized = "table"

                [targets.prod]
                schema = "${{CTX:model.schema}}"

                [targets.dev]
                schema = "dev"
                reuse_from = "prod"
                reuse_hard_copy = true
                """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    expression: SELECT 1 AS order_id, 100 AS amount_cents
                    freshness:
                      strategy: sql
                      type: integer
                      query: SELECT 1 AS data_version
                """
            ).strip()
            + "\n",
            "models/staging/stg_orders.sql": dedent(
                """
                MODEL (materialized table, tags [staging]);

                SELECT order_id, amount_cents FROM __source("raw_orders")
                """
            ).strip()
            + "\n",
            "models/intermediate/int_orders.sql": dedent(
                """
                MODEL (materialized table, tags [intermediate]);

                SELECT order_id, amount_cents + 25 AS amount_cents FROM __ref("stg_orders")
                """
            ).strip()
            + "\n",
            "models/marts/fact_orders.sql": dedent(
                """
                MODEL (materialized table, tags [marts]);

                SELECT order_id, amount_cents / 100.0 AS amount_dollars FROM __ref("int_orders")
                """
            ).strip()
            + "\n",
        },
    )


def write_direct_changes_only_stg_orders(*, project_dir: Path, amount_cents: int) -> None:
    (project_dir / "models" / "stg_orders.sql").write_text(
        direct_changes_only_stg_orders_sql(amount_cents=amount_cents),
        encoding="utf-8",
    )


def direct_changes_only_stg_orders_sql(*, amount_cents: int) -> str:
    return (
        "MODEL (materialized table);\n\n"
        "SELECT\n"
        "  1 AS order_id,\n"
        f"  {amount_cents} AS amount_cents\n"
    )
