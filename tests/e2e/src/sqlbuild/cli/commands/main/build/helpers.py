from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DeferCloneBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


def run_replay_command(
    *, command: tuple[str, ...], project_dir: Path
) -> subprocess.CompletedProcess[str]:
    """Run a successful replay lifecycle command and retain its output."""
    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", *command), project_dir=project_dir
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def replay_order_rows(*, db_path: Path, table: str) -> list[tuple[object, ...]]:
    """Read complete replay results in deterministic order."""
    return query_duckdb(
        db_path=db_path, sql=f"SELECT order_date, amount_cents FROM main.{table} ORDER BY 1"
    )


def capped_microbatch_project_files(
    *, limit_action: str, project_limit: str = ""
) -> dict[str, str]:
    """Build a direct DuckDB project with one capped producer and plain consumer."""

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
            MODEL (materialized view);
            SELECT id, event_time
            FROM __ref("capped_events")
            """
        ).strip()
        + "\n",
    }


def capped_watermark_consumer_project_files(*, limit_action: str) -> dict[str, str]:
    """Build an invalid project whose watermark consumer reads a capped producer."""

    repo_files: dict[str, str] = capped_microbatch_project_files(limit_action=limit_action)
    repo_files["models/downstream_events.sql"] = (
        dedent(
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
        + "\n"
    )
    return repo_files


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


def dropped_incremental_project_files(*, incremental_strategy: str) -> dict[str, str]:
    """Return a DuckDB project with one timestamp-cursor incremental order model."""

    return {
        "sqlbuild_project.toml": (
            'name = "dropped_orders"\nadapter = "duckdb"\n\n'
            '[connection]\ndatabase = "dropped_orders.duckdb"\n'
        ),
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "models/orders.sql": (
            "MODEL (\n"
            "  materialized incremental,\n"
            f"  incremental_strategy {incremental_strategy},\n"
            "  unique_key id,\n"
            "  cursor ordered_at,\n"
            "  cursor_type timestamp,\n"
            "  cursor_grain day,\n"
            "  cursor_start '2026-01-02',\n"
            ");\n\n"
            'SELECT id, ordered_at FROM __source("raw_orders")\n'
        ),
    }
