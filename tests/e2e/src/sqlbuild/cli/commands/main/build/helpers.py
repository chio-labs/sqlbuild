from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Any

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DeferCloneBuildE2ETestCase,
    NodeSourceWatermarkBuildE2ETestCase,
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


def prepare_node_source_watermark_project(
    *,
    tmp_path: Path,
    project_name: str,
    models: dict[str, str],
) -> Path:
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
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: main
                    table: raw_orders
                    freshness:
                      strategy: sql
                      type: integer
                      query: SELECT MAX(data_version) AS data_version FROM raw_orders
                """
            ).strip()
            + "\n",
            **models,
        },
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


def latest_node_source_watermark_payloads(*, db_path: Path) -> dict[str, dict[str, Any]]:
    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_name, watermarks_json_b64 FROM main._sqlbuild_node_source_watermarks "
            "ORDER BY created_at, run_id, node_name"
        ),
    )
    payloads: dict[str, dict[str, Any]] = {}
    node_name: Any
    encoded_payload: Any
    for node_name, encoded_payload in rows:
        payloads[str(node_name)] = json.loads(
            base64.b64decode(str(encoded_payload)).decode("utf-8")
        )
    return payloads


def build_frontier_inputs_for_node_source_watermark_case(
    *,
    project_dir: Path,
    db_path: Path,
    test_case: NodeSourceWatermarkBuildE2ETestCase,
) -> None:
    versions: tuple[int, ...]
    commands: tuple[tuple[str, ...], ...]
    for versions, commands in test_case.frontier_actions:
        replace_raw_orders_versions(db_path=db_path, versions=versions)
        for command in commands:
            run_successful_sqb_build(project_dir=project_dir, command=command)


def run_successful_sqb_build(*, project_dir: Path, command: tuple[str, ...]) -> None:
    result: subprocess.CompletedProcess[str] = run_sqb(command=command, project_dir=project_dir)
    assert result.returncode == 0, result.stdout + result.stderr


def node_source_watermark_versions_by_node(
    *,
    payloads: dict[str, dict[str, Any]],
    test_case: NodeSourceWatermarkBuildE2ETestCase,
) -> dict[str, tuple[str, ...]]:
    versions_by_node: dict[str, tuple[str, ...]] = {}
    for name in test_case.expected_source_versions_by_node:
        versions: list[str] = []
        for entry in payloads[name]["sources"]:
            versions.append(str(entry["data_version"]))
        versions_by_node[name] = tuple(versions)
    return versions_by_node


def node_source_watermark_kinds_by_node(
    *,
    payloads: dict[str, dict[str, Any]],
    test_case: NodeSourceWatermarkBuildE2ETestCase,
) -> dict[str, tuple[str, ...]]:
    kinds_by_node: dict[str, tuple[str, ...]] = {}
    for name in test_case.expected_source_kinds_by_node:
        kinds: list[str] = []
        for entry in payloads[name]["sources"]:
            kinds.append(str(entry["watermark_kind"]))
        kinds_by_node[name] = tuple(kinds)
    return kinds_by_node


def node_source_watermark_unknown_reasons_by_node(
    *,
    payloads: dict[str, dict[str, Any]],
    test_case: NodeSourceWatermarkBuildE2ETestCase,
) -> dict[str, tuple[str, ...]]:
    reasons_by_node: dict[str, tuple[str, ...]] = {}
    for name in test_case.expected_unknown_reasons_by_node:
        reasons: list[str] = []
        for entry in payloads[name]["unknown_sources"]:
            reasons.append(str(entry["reason"]))
        reasons_by_node[name] = tuple(reasons)
    return reasons_by_node


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
              cursor_inputs (),
              replay_on_change bounded-7d
            );

            SELECT id, ordered_at, {amount_expression} AS amount_cents
            FROM __source("raw_orders")
            """
        ).strip()
        + "\n"
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


def prepare_direct_reuse_from_audit_project(*, tmp_path: Path, project_name: str) -> Path:
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
            "models/orders.sql": dedent(
                """
                MODEL (
                  materialized table,
                  audits [
                    expression_is_true (
                      name "id is present",
                      expression "id IS NOT NULL",
                      severity error,
                    ),
                  ],
                );

                SELECT 1 AS id
                """
            ).strip()
            + "\n",
            "audits/generic/expression_is_true.sql": dedent(
                """
                AUDIT ();

                SELECT * FROM __ref("@model") WHERE NOT (@expression)
                """
            ).strip()
            + "\n",
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
                        connection=ctx.connection,
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
