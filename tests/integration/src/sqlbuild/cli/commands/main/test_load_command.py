from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb
import pytest
from _pytest.capture import CaptureFixture, CaptureResult
from duckdb import DuckDBPyConnection

from sqlbuild.cli.commands.main.load import run_load
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    LoadCommandIntegrationTestCase,
)

LOAD_COMMAND_TEST_CASES: list[LoadCommandIntegrationTestCase] = [
    LoadCommandIntegrationTestCase(
        description="loads returned dict rows into a source table",
        project_files={
            "sqlbuild_project.toml": (
                'name = "demo"\nadapter = "duckdb"\n\n[connection]\ndatabase = "demo.duckdb"\n'
            ),
            "sources/raw.yml": """
sources:
  - name: raw_orders
    loader: raw_orders_loader
    write_strategy: table
    columns:
      - name: order_id
        type: INTEGER
      - name: status
        type: VARCHAR
""".strip()
            + "\n",
            "loaders/raw_orders.py": """
from sqlbuild.loaders import loader

@loader
def raw_orders_loader(ctx):
    ctx.log("loading raw orders")
    return [
        {"order_id": 1, "status": "placed"},
        {"order_id": 2, "status": "shipped"},
    ]
""",
        },
        expected_exit_code=0,
        expected_rows=((1, "placed"), (2, "shipped")),
        expected_stdout_fragment="raw_orders",
    ),
    LoadCommandIntegrationTestCase(
        description="loads only selected managed source",
        project_files={
            "sqlbuild_project.toml": (
                'name = "demo"\nadapter = "duckdb"\n\n[connection]\ndatabase = "demo.duckdb"\n'
            ),
            "sources/raw.yml": """
sources:
  - name: raw_orders
    loader: raw_orders_loader
    write_strategy: table
    columns:
      - name: order_id
        type: INTEGER
      - name: status
        type: VARCHAR
  - name: raw_events
    loader: raw_events_loader
    write_strategy: table
""".strip()
            + "\n",
            "loaders/raw_orders.py": """
from sqlbuild.loaders import loader

@loader
def raw_orders_loader(ctx):
    return [{"order_id": 3, "status": "selected"}]
""",
            "loaders/raw_events.py": """
from sqlbuild.loaders import loader

@loader
def raw_events_loader(ctx):
    return [{"event_id": 99}]
""",
        },
        expected_exit_code=0,
        expected_rows=((3, "selected"),),
        expected_stdout_fragment="raw_orders",
        expected_stdout_absent_fragments=("raw_events",),
        select=("raw_orders",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    LOAD_COMMAND_TEST_CASES,
    ids=[case.description for case in LOAD_COMMAND_TEST_CASES],
)
def test_given_source_loader_when_running_load_then_writes_source_table(
    test_case: LoadCommandIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    capsys: CaptureFixture[str],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    exit_code: int = run_load(project_dir=tmp_path, no_color=True, select=test_case.select)

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stdout_fragment in captured.out
    assert all(
        fragment not in captured.out for fragment in test_case.expected_stdout_absent_fragments
    )
    connection: DuckDBPyConnection = duckdb.connect(str(tmp_path / "demo.duckdb"))
    try:
        rows: tuple[tuple[object, ...], ...] = tuple(
            connection.execute(
                "SELECT order_id, status FROM raw_orders ORDER BY order_id"
            ).fetchall()
        )
    finally:
        connection.close()
    assert rows == test_case.expected_rows
