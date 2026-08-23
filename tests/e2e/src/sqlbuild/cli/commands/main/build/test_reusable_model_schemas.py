"""E2E coverage for reusable model schemas across materializations."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import duckdb
import pytest

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


def test_given_reusable_inherited_schemas_when_building_then_all_materializations_succeed(
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="reusable_schema_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "reusable_schema_project"
                adapter = "duckdb"

                [connection]
                database = "reusable_schema.duckdb"
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
            "schemas/events/base.sql": dedent(
                """
                SCHEMA (
                  name event,
                  columns (
                    event_id (type INTEGER, nullable false),
                    observed_at (type TIMESTAMP, nullable false),
                  ),
                );
                """
            ).strip()
            + "\n",
            "schemas/events/sourced.sql": dedent(
                """
                SCHEMA (
                  name sourced_event,
                  extends event,
                  columns (
                    source (type VARCHAR, nullable false),
                  ),
                );
                """
            ).strip()
            + "\n",
            "models/stg_events.sql": dedent(
                """
                MODEL (
                  materialized view,
                  model_schema event,
                  contract enforced,
                );

                SELECT
                  event_id,
                  observed_at
                FROM __source("raw_events")
                """
            ).strip()
            + "\n",
            "models/event_table.sql": dedent(
                """
                MODEL (
                  materialized table,
                  model_schema sourced_event,
                  contract enforced,
                );

                SELECT
                  event_id,
                  observed_at,
                  'feed'::VARCHAR AS source
                FROM __ref("stg_events")
                """
            ).strip()
            + "\n",
            "models/event_incremental.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy append,
                  cursor observed_at,
                  cursor_type timestamp,
                  cursor_grain second,
                  model_schema sourced_event,
                  contract enforced,
                );

                SELECT
                  event_id,
                  observed_at,
                  source
                FROM __ref("event_table")
                """
            ).strip()
            + "\n",
        },
    )
    database_path: Path = project_dir / "reusable_schema.duckdb"
    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(database_path))
    connection.execute(
        """
        CREATE TABLE raw_events (event_id INTEGER NOT NULL, observed_at TIMESTAMP NOT NULL);
        INSERT INTO raw_events VALUES (1, '2026-01-01 00:00:00');
        """
    )
    connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    connection = duckdb.connect(str(database_path))
    rows: list[tuple[int, str]] = connection.execute(
        "SELECT event_id, source FROM event_incremental ORDER BY event_id"
    ).fetchall()
    connection.close()
    assert rows == [(1, "feed")]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
