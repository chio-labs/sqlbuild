"""E2E regression tests for append cursor rerun behavior."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    AppendCursorBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AppendCursorBuildE2ETestCase(
            description=(
                "default inclusive append cursor rerun duplicates boundary row "
                "and captures late same-timestamp row"
            ),
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """

                name = "append_cursor_project"

                adapter = "duckdb"



                [connection]

                database = "append_cursor.duckdb"



                [defaults]

                materialized = "table"

                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_orders
                        schema: main
                        table: raw_orders
                    """
                ).strip()
                + "\n",
                "models/orders.sql": dedent(
                    """
                    MODEL (
                      materialized incremental,
                      incremental_strategy append,
                      cursor ordered_at,
                      cursor_type timestamp,
                      cursor_grain second,
                    );

                    SELECT id, ordered_at
                    FROM __source("raw_orders")
                    """
                ).strip()
                + "\n",
            },
            initial_seed_sql=dedent(
                """
                CREATE TABLE main.raw_orders (id INTEGER, ordered_at TIMESTAMP);

                INSERT INTO main.raw_orders VALUES
                  (1, '2026-01-01 00:00:00'),
                  (2, '2026-01-01 01:00:00');
                """
            ).strip(),
            mutation_sql=(
                "INSERT INTO main.raw_orders VALUES (3, '2026-01-01 01:00:00')",
                "INSERT INTO main.raw_orders VALUES (4, '2026-01-01 02:00:00')",
            ),
            command=("--no-color", "build"),
            expected_exit_code=0,
            expected_runtime_sql_fragment=(
                "WHERE ordered_at >= TIMESTAMP '2026-01-01 00:00:00' "
                "AND ordered_at < TIMESTAMP '2026-01-01 02:00:00'"
            ),
            expected_query_results=(
                (
                    (
                        "SELECT id, CAST(ordered_at AS VARCHAR) "
                        "FROM main.orders ORDER BY id, ordered_at"
                    ),
                    (
                        (1, "2026-01-01 00:00:00"),
                        (1, "2026-01-01 00:00:00"),
                        (2, "2026-01-01 01:00:00"),
                        (3, "2026-01-01 01:00:00"),
                    ),
                ),
            ),
        )
    ],
    ids=[
        (
            "default inclusive append cursor rerun duplicates boundary row "
            "and captures late same-timestamp row"
        )
    ],
)
def test_given_append_cursor_project_when_rerunning_build_then_boundary_behavior_matches_expected(
    test_case: AppendCursorBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="append_cursor_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "append_cursor.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute(test_case.initial_seed_sql)
    connection.close()

    first_result: object = run_sqb(command=test_case.command, project_dir=project_dir)
    assert first_result.returncode == test_case.expected_exit_code, (
        first_result.stdout + first_result.stderr
    )

    connection = duckdb.connect(str(db_path))
    statement: str
    for statement in test_case.mutation_sql:
        connection.execute(statement)
    connection.close()

    second_result: object = run_sqb(command=test_case.command, project_dir=project_dir)
    assert second_result.returncode == test_case.expected_exit_code, (
        second_result.stdout + second_result.stderr
    )

    runtime_sql: str = (project_dir / "target" / "run" / "models" / "orders.sql").read_text(
        encoding="utf-8"
    )
    assert test_case.expected_runtime_sql_fragment in runtime_sql

    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        actual_rows: list[tuple[object, ...]] = query_duckdb(db_path=db_path, sql=query)
        assert tuple(tuple(row) for row in actual_rows) == expected_rows
