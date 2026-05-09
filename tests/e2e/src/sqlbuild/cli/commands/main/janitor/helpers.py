"""Helpers for janitor e2e tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from textwrap import dedent

from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_inline_project


def prepare_janitor_project(
    *,
    tmp_path: Path,
    project_name: str,
    janitor_config: str = "",
    settings_config: str = "",
) -> Path:
    """Create a minimal DuckDB project for janitor e2e tests."""

    normalized_settings_config: str = dedent(settings_config).strip()
    normalized_janitor_config: str = dedent(janitor_config).strip()
    settings_block: str = (
        f"\n[settings]\n{normalized_settings_config}\n" if normalized_settings_config else ""
    )
    janitor_block: str = (
        f"\n[janitor]\n{normalized_janitor_config}\n" if normalized_janitor_config else ""
    )
    project_config: str = (
        f'name = "{project_name}"\n'
        'adapter = "duckdb"\n\n'
        "[connection]\n"
        'database = "janitor.duckdb"\n'
        f"{settings_block}"
        f"{janitor_block}"
        "\n[defaults]\n"
        'materialized = "table"\n'
    )
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": project_config,
            "models/orders.sql": dedent(
                """
                MODEL ();

                SELECT 1 AS order_id
                """
            ).strip()
            + "\n",
        },
    )


def create_janitor_demo_relations(*, db_path: Path) -> None:
    """Create tracked, untracked, and excluded stale relations."""

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE janitor_tracked_extra AS SELECT 1 AS id")
        connection.execute("CREATE TABLE janitor_untracked_extra AS SELECT 1 AS id")
        connection.execute("CREATE TABLE partition_state AS SELECT 1 AS id")
        write_fingerprint(
            connection=connection,
            execute=lambda active_connection, sql: active_connection.execute(sql),
            database=None,
            schema="main",
            fingerprint=Fingerprint(
                model_name="janitor_tracked_extra",
                target_database=None,
                target_schema="main",
                target_name="janitor_tracked_extra",
                run_id="run_janitor_e2e",
                query_hash="query_hash",
                ast_hash=None,
                schema_fingerprint="schema_hash",
                query_sql="SELECT 1 AS id",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
            render_qualified_name=DuckDbAdapter().render_qualified_name,
            render_framework_type=DuckDbAdapter().render_framework_type,
        )
    finally:
        connection.close()


def create_janitor_scenario_relations(*, db_path: Path) -> None:
    """Create strict scenario artifacts and a similarly named non-artifact relation."""

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE __sqb_a13f09c2e7b8__source__raw_orders AS SELECT 1 AS id")
        connection.execute(
            "CREATE TABLE __sqb_a13f09c2e7b8__model__daily_revenue AS SELECT 1 AS id"
        )
        connection.execute("CREATE TABLE __sqb_a13f09c2e7b__model__daily_revenue AS SELECT 1 AS id")
    finally:
        connection.close()
