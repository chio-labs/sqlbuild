"""Helpers for janitor e2e tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from textwrap import dedent, indent

from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_inline_project


def prepare_janitor_project(
    *,
    tmp_path: Path,
    project_name: str,
    janitor_config: str = "",
    settings_config: str = "",
) -> Path:
    """Create a minimal DuckDB project for janitor e2e tests."""

    normalized_settings_config: str = _normalize_nested_yaml(settings_config)
    normalized_janitor_config: str = _normalize_nested_yaml(janitor_config)
    settings_block: str = (
        f"\nsettings:\n{normalized_settings_config}" if normalized_settings_config else ""
    )
    janitor_block: str = (
        f"\njanitor:\n{normalized_janitor_config}" if normalized_janitor_config else ""
    )
    project_config: str = (
        f"name: {project_name}\n"
        "adapter: duckdb\n\n"
        "connection:\n"
        "  database: janitor.duckdb\n"
        f"{settings_block}"
        f"{janitor_block}"
        "\n\ndefaults:\n"
        "  materialized: table\n"
    )
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.yml": project_config,
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
        )
    finally:
        connection.close()


def _normalize_nested_yaml(contents: str) -> str:
    if not contents:
        return ""
    return indent(dedent(contents).strip("\n"), "  ")
