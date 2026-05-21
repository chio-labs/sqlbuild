from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import duckdb
import pytest
from _pytest.capture import CaptureFixture, CaptureResult
from duckdb import DuckDBPyConnection

from sqlbuild.cli.commands.main.load import run_load
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.execution_json import format_load_execution_json
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSourceFile
from sqlbuild.executor.load.main.run import run_load_pipeline
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    LoadCommandConcurrencyTestCase,
    LoadCommandEmptyRowsTestCase,
    LoadCommandEmptySelectionTestCase,
    LoadCommandFailureTestCase,
    LoadCommandInferredColumnsTestCase,
    LoadCommandIntegrationTestCase,
    LoadCommandMultipleYieldTestCase,
    LoadCommandSelectionErrorTestCase,
)

_PROJECT_FILE: str = 'name = "demo"\nadapter = "duckdb"\n\n[connection]\ndatabase = "demo.duckdb"\n'

_RAW_ORDERS_LOADER: str = """
from sqlbuild.loaders import loader

@loader
def raw_orders_loader(ctx):
    return [{"order_id": 1, "status": "loaded"}]
"""

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
        expected_stdout_fragments=(
            "Load ready (1 selected)",
            "Sources (1)",
            "Execution  sqb load  (concurrency: 1)",
            "1/1  source    raw_orders",
            "Completed successfully.",
            "PASS=1  WARN=0  FAIL=0  SKIP=0  TOTAL=1",
        ),
        expected_json_staging_relation="raw_orders__staging",
        expected_lifecycle_sql_fragments=(
            "CREATE OR REPLACE TABLE raw_orders__staging",
            "CREATE OR REPLACE TABLE raw_orders AS SELECT * FROM raw_orders__staging",
            "DROP TABLE IF EXISTS raw_orders__staging",
        ),
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
        expected_json_staging_relation="raw_orders__staging",
        expected_lifecycle_sql_fragments=(
            "CREATE OR REPLACE TABLE raw_orders__staging",
            "CREATE OR REPLACE TABLE raw_orders AS SELECT * FROM raw_orders__staging",
            "DROP TABLE IF EXISTS raw_orders__staging",
        ),
        select=("raw_orders",),
    ),
    LoadCommandIntegrationTestCase(
        description="passes effective context values to loader",
        project_files={
            "sqlbuild_project.toml": (
                'name = "demo"\n'
                'adapter = "duckdb"\n'
                'default_environment = "dev"\n\n'
                "[connection]\n"
                'database = "demo.duckdb"\n\n'
                "[vars]\n"
                'tier = "project"\n'
                'project_only = "yes"\n\n'
                "[environments.dev.vars]\n"
                'tier = "dev"\n'
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
    status = ":".join([
        str(ctx.environment),
        str(ctx.vars["tier"]),
        str(ctx.vars["project_only"]),
        str(ctx.run_id != "demo"),
    ])
    return [{
        "order_id": 4,
        "status": status,
    }]
""",
        },
        expected_exit_code=0,
        expected_rows=((4, "dev:cli:yes:True"),),
        expected_stdout_fragment="raw_orders",
        expected_json_staging_relation="raw_orders__staging",
        expected_lifecycle_sql_fragments=(
            "CREATE OR REPLACE TABLE raw_orders__staging",
            "CREATE OR REPLACE TABLE raw_orders AS SELECT * FROM raw_orders__staging",
            "DROP TABLE IF EXISTS raw_orders__staging",
        ),
        cli_vars={"tier": "cli"},
    ),
]

LOAD_SELECTION_ERROR_TEST_CASES: list[LoadCommandSelectionErrorTestCase] = [
    LoadCommandSelectionErrorTestCase(
        description="raises when selected source does not exist",
        project_files={
            "sqlbuild_project.toml": _PROJECT_FILE,
            "sources/raw.yml": """
sources:
  - name: raw_orders
    loader: raw_orders_loader
    write_strategy: table
""".strip()
            + "\n",
            "loaders/raw_orders.py": _RAW_ORDERS_LOADER,
        },
        select=("missing_source",),
        exclude=(),
        expected_error_fragment="selector 'missing_source' does not match any source",
    ),
    LoadCommandSelectionErrorTestCase(
        description="raises when selected source is unmanaged",
        project_files={
            "sqlbuild_project.toml": _PROJECT_FILE,
            "sources/raw.yml": """
sources:
  - name: raw_customers
    expression: SELECT 1 AS customer_id
""".strip()
            + "\n",
        },
        select=("raw_customers",),
        exclude=(),
        expected_error_fragment="selector 'raw_customers' matches a source with no loader",
    ),
    LoadCommandSelectionErrorTestCase(
        description="raises when excluded source does not exist",
        project_files={
            "sqlbuild_project.toml": _PROJECT_FILE,
            "sources/raw.yml": """
sources:
  - name: raw_orders
    loader: raw_orders_loader
    write_strategy: table
""".strip()
            + "\n",
            "loaders/raw_orders.py": _RAW_ORDERS_LOADER,
        },
        select=(),
        exclude=("missing_source",),
        expected_error_fragment="selector 'missing_source' does not match any source",
    ),
    LoadCommandSelectionErrorTestCase(
        description="raises when excluded source is unmanaged",
        project_files={
            "sqlbuild_project.toml": _PROJECT_FILE,
            "sources/raw.yml": """
sources:
  - name: raw_orders
    loader: raw_orders_loader
    write_strategy: table
  - name: raw_customers
    expression: SELECT 1 AS customer_id
""".strip()
            + "\n",
            "loaders/raw_orders.py": _RAW_ORDERS_LOADER,
        },
        select=(),
        exclude=("raw_customers",),
        expected_error_fragment="selector 'raw_customers' matches a source with no loader",
    ),
]

EMPTY_SELECTION_TEST_CASES: list[LoadCommandEmptySelectionTestCase] = [
    LoadCommandEmptySelectionTestCase(
        description="succeeds without connecting when project has no managed sources",
        project_files={
            "sqlbuild_project.toml": _PROJECT_FILE,
            "sources/raw.yml": """
sources:
  - name: raw_customers
    expression: SELECT 1 AS customer_id
""".strip()
            + "\n",
        },
        select=(),
        exclude=(),
        expected_exit_code=0,
        expected_stdout_fragment="No managed sources selected.",
        expected_stdout_fragments=(
            "Load ready (0 selected)",
            "Completed successfully.",
            "PASS=0  WARN=0  FAIL=0  SKIP=0  TOTAL=0",
        ),
    ),
    LoadCommandEmptySelectionTestCase(
        description="succeeds without connecting when all managed sources are excluded",
        project_files={
            "sqlbuild_project.toml": _PROJECT_FILE,
            "sources/raw.yml": """
sources:
  - name: raw_orders
    loader: raw_orders_loader
    write_strategy: table
""".strip()
            + "\n",
            "loaders/raw_orders.py": _RAW_ORDERS_LOADER,
        },
        select=(),
        exclude=("raw_orders",),
        expected_exit_code=0,
        expected_stdout_fragment="No managed sources selected.",
        expected_stdout_fragments=(
            "Load ready (0 selected)",
            "Completed successfully.",
            "PASS=0  WARN=0  FAIL=0  SKIP=0  TOTAL=0",
        ),
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
    json_output_path: Path = tmp_path / "target" / "load.json"

    exit_code: int = run_load(
        project_dir=tmp_path,
        no_color=True,
        select=test_case.select,
        cli_vars=test_case.cli_vars,
        json_output_path=json_output_path,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stdout_fragment in captured.out
    assert all(fragment in captured.out for fragment in test_case.expected_stdout_fragments)
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
        staging_exists: bool = (
            connection.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'raw_orders__staging'"
            ).fetchone()
            is not None
        )
    finally:
        connection.close()
    assert rows == test_case.expected_rows
    assert not staging_exists
    payload: dict[str, Any] = cast(
        dict[str, Any], json.loads(json_output_path.read_text(encoding="utf-8"))
    )
    assets: list[dict[str, Any]] = cast(list[dict[str, Any]], payload["assets"])
    assert assets[0]["staging_relation"] == test_case.expected_json_staging_relation


@pytest.mark.parametrize(
    "test_case",
    LOAD_COMMAND_TEST_CASES,
    ids=[case.description for case in LOAD_COMMAND_TEST_CASES],
)
def test_given_source_loader_when_running_pipeline_then_uses_staging_relation(
    test_case: LoadCommandIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    source_file: DiscoveredSourceFile = discovered_inputs.source_files[0]
    adapter: DuckDbAdapter = DuckDbAdapter()

    results: tuple[LoadExecutionResult, ...] = run_load_pipeline(
        sources=source_file.source_entries,
        loader_functions=discovered_inputs.loader_functions,
        connection_config={"database": str(tmp_path / "demo.duckdb")},
        adapter=adapter,
        run_id="test_run",
        environment="dev",
        vars={"tier": "cli", "project_only": "yes"},
        is_reload=False,
    )

    lifecycle_sql: tuple[str, ...] = tuple(
        event.content for event in results[0].lifecycle_events if event.kind.value == "sql"
    )
    assert all(
        any(fragment in sql for sql in lifecycle_sql)
        for fragment in test_case.expected_lifecycle_sql_fragments
    )


@pytest.mark.parametrize(
    "test_case",
    [
        LoadCommandConcurrencyTestCase(
            description="uses bounded concurrent connections and preserves result order",
            project_files={
                "sqlbuild_project.toml": _PROJECT_FILE,
                "sources/raw.yml": """
sources:
  - name: raw_a
    loader: raw_a_loader
    write_strategy: table
    columns:
      - name: source_name
        type: VARCHAR
      - name: connection_id
        type: BIGINT
  - name: raw_b
    loader: raw_b_loader
    write_strategy: table
    columns:
      - name: source_name
        type: VARCHAR
      - name: connection_id
        type: BIGINT
  - name: raw_c
    loader: raw_c_loader
    write_strategy: table
    columns:
      - name: source_name
        type: VARCHAR
      - name: connection_id
        type: BIGINT
""".strip()
                + "\n",
                "loaders/raw.py": """
import threading
import time

from sqlbuild.loaders import loader

barrier = threading.Barrier(2)

@loader
def raw_a_loader(ctx):
    barrier.wait(timeout=1)
    time.sleep(0.05)
    return [{"source_name": "raw_a", "connection_id": id(ctx.connection)}]

@loader
def raw_b_loader(ctx):
    barrier.wait(timeout=1)
    return [{"source_name": "raw_b", "connection_id": id(ctx.connection)}]

@loader
def raw_c_loader(ctx):
    return [{"source_name": "raw_c", "connection_id": id(ctx.connection)}]
""",
            },
            max_concurrency=2,
            expected_connection_count=2,
            expected_source_order=("raw_a", "raw_b", "raw_c"),
            expected_json_asset_order=("raw_a", "raw_b", "raw_c"),
        ),
    ],
    ids=["uses bounded concurrent connections and preserves result order"],
)
def test_given_multiple_source_loaders_when_running_pipeline_then_uses_concurrent_connections(
    test_case: LoadCommandConcurrencyTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    source_file: DiscoveredSourceFile = discovered_inputs.source_files[0]
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection_starts: list[int] = []

    results: tuple[LoadExecutionResult, ...] = run_load_pipeline(
        sources=source_file.source_entries,
        loader_functions=discovered_inputs.loader_functions,
        connection_config={"database": str(tmp_path / "demo.duckdb")},
        adapter=adapter,
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
        max_concurrency=test_case.max_concurrency,
        on_connection_start=connection_starts.append,
    )

    assert connection_starts == [test_case.expected_connection_count]
    assert tuple(result.source_name for result in results) == test_case.expected_source_order
    payload: dict[str, Any] = cast(
        dict[str, Any], json.loads(format_load_execution_json(results=results))
    )
    assets: list[dict[str, Any]] = cast(list[dict[str, Any]], payload["assets"])
    assert tuple(asset["name"] for asset in assets) == test_case.expected_json_asset_order
    connection: DuckDBPyConnection = duckdb.connect(str(tmp_path / "demo.duckdb"))
    try:
        first_row: tuple[int] | None = connection.execute(
            "SELECT connection_id FROM raw_a"
        ).fetchone()
        second_row: tuple[int] | None = connection.execute(
            "SELECT connection_id FROM raw_b"
        ).fetchone()
    finally:
        connection.close()
    assert first_row is not None
    assert second_row is not None
    first_connection_id: int = first_row[0]
    second_connection_id: int = second_row[0]
    assert first_connection_id != second_connection_id


@pytest.mark.parametrize(
    "test_case",
    [
        LoadCommandInferredColumnsTestCase(
            description="loads generator rows with declared missing and inferred extra columns",
            project_files={
                "sqlbuild_project.toml": _PROJECT_FILE,
                "sources/raw.yml": """
sources:
  - name: raw_inferred
    loader: raw_inferred_loader
    write_strategy: table
    columns:
      - name: id
        type: INTEGER
      - name: notes
        type: VARCHAR
""".strip()
                + "\n",
                "loaders/raw.py": """
from datetime import date, datetime

from sqlbuild.loaders import loader

@loader
def raw_inferred_loader(ctx):
    yield {
        "id": 1,
        "flag": True,
        "amount": 2.5,
        "name": "customer's order",
        "payload": {"source": "loader"},
        "tags": ["new", "priority"],
        "created_at": datetime(2026, 5, 21, 12, 30, 0),
        "service_date": date(2026, 5, 21),
    }
""",
            },
            expected_row=(
                1,
                None,
                True,
                2.5,
                "customer's order",
                '{"source": "loader"}',
                '["new", "priority"]',
                datetime(2026, 5, 21, 12, 30, 0),
                date(2026, 5, 21),
            ),
            expected_column_types={
                "id": "INTEGER",
                "notes": "VARCHAR",
                "flag": "BOOLEAN",
                "amount": "DOUBLE",
                "name": "VARCHAR",
                "payload": "JSON",
                "tags": "JSON",
                "created_at": "TIMESTAMP",
                "service_date": "DATE",
            },
        ),
    ],
    ids=["loads generator rows with declared missing and inferred extra columns"],
)
def test_given_generator_loader_with_inferred_columns_when_running_load_then_writes_schema_and_data(
    test_case: LoadCommandInferredColumnsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    exit_code: int = run_load(project_dir=tmp_path, no_color=True)

    assert exit_code == 0
    connection: DuckDBPyConnection = duckdb.connect(str(tmp_path / "demo.duckdb"))
    try:
        row: tuple[object, ...] | None = connection.execute(
            "SELECT id, notes, flag, amount, name, CAST(payload AS VARCHAR), "
            "CAST(tags AS VARCHAR), created_at, service_date "
            "FROM raw_inferred"
        ).fetchone()
        column_rows: list[tuple[str, str]] = connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'raw_inferred'"
        ).fetchall()
    finally:
        connection.close()
    assert row == test_case.expected_row
    column_types: dict[str, str] = dict(column_rows)
    expected_column: str
    for expected_column, expected_type in test_case.expected_column_types.items():
        assert column_types[expected_column] == expected_type


@pytest.mark.parametrize(
    "test_case",
    [
        LoadCommandMultipleYieldTestCase(
            description="loads every row yielded by a generator loader",
            project_files={
                "sqlbuild_project.toml": _PROJECT_FILE,
                "sources/raw.yml": """
sources:
  - name: raw_multi_yield
    loader: raw_multi_yield_loader
    write_strategy: table
    columns:
      - name: id
        type: INTEGER
      - name: status
        type: VARCHAR
""".strip()
                + "\n",
                "loaders/raw.py": """
from sqlbuild.loaders import loader

@loader
def raw_multi_yield_loader(ctx):
    yield {"id": 1, "status": "first"}
    yield {"id": 2, "status": "second"}
""",
            },
            expected_rows=((1, "first"), (2, "second")),
        ),
    ],
    ids=["loads every row yielded by a generator loader"],
)
def test_given_generator_loader_yields_multiple_rows_when_running_load_then_writes_all_rows(
    test_case: LoadCommandMultipleYieldTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    exit_code: int = run_load(project_dir=tmp_path, no_color=True)

    assert exit_code == 0
    connection: DuckDBPyConnection = duckdb.connect(str(tmp_path / "demo.duckdb"))
    try:
        rows: list[tuple[object, ...]] = connection.execute(
            "SELECT id, status FROM raw_multi_yield ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    assert tuple(rows) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        LoadCommandEmptyRowsTestCase(
            description="loads empty returned rows into declared empty table",
            project_files={
                "sqlbuild_project.toml": _PROJECT_FILE,
                "sources/raw.yml": """
sources:
  - name: raw_empty
    loader: raw_empty_loader
    write_strategy: table
    columns:
      - name: id
        type: INTEGER
      - name: status
        type: VARCHAR
""".strip()
                + "\n",
                "loaders/raw.py": """
from sqlbuild.loaders import loader

@loader
def raw_empty_loader(ctx):
    return []
""",
            },
            expected_column_types={"id": "INTEGER", "status": "VARCHAR"},
        ),
    ],
    ids=["loads empty returned rows into declared empty table"],
)
def test_given_loader_returns_empty_rows_when_running_load_then_writes_empty_declared_table(
    test_case: LoadCommandEmptyRowsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    exit_code: int = run_load(project_dir=tmp_path, no_color=True)

    assert exit_code == 0
    connection: DuckDBPyConnection = duckdb.connect(str(tmp_path / "demo.duckdb"))
    try:
        row_count_row: tuple[int] | None = connection.execute(
            "SELECT COUNT(*) FROM raw_empty"
        ).fetchone()
        column_rows: list[tuple[str, str]] = connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'raw_empty'"
        ).fetchall()
    finally:
        connection.close()
    assert row_count_row is not None
    row_count: int = row_count_row[0]
    assert row_count == 0
    assert dict(column_rows) == test_case.expected_column_types


@pytest.mark.parametrize(
    "test_case",
    [
        LoadCommandFailureTestCase(
            description="fails clearly when returned rows contain conflicting inferred types",
            project_files={
                "sqlbuild_project.toml": _PROJECT_FILE,
                "sources/raw.yml": """
sources:
  - name: raw_conflict
    loader: raw_conflict_loader
    write_strategy: table
""".strip()
                + "\n",
                "loaders/raw.py": """
from sqlbuild.loaders import loader

@loader
def raw_conflict_loader(ctx):
    return [
        {"id": 1},
        {"id": "two"},
    ]
""",
            },
            expected_exit_code=1,
            expected_stdout_fragment="conflicting types for column 'id'",
        ),
    ],
    ids=["fails clearly when returned rows contain conflicting inferred types"],
)
def test_given_loader_returns_conflicting_types_when_running_load_then_fails_clearly(
    test_case: LoadCommandFailureTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    capsys: CaptureFixture[str],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    exit_code: int = run_load(project_dir=tmp_path, no_color=True)

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stdout_fragment in captured.out


@pytest.mark.parametrize(
    "test_case",
    LOAD_SELECTION_ERROR_TEST_CASES,
    ids=[case.description for case in LOAD_SELECTION_ERROR_TEST_CASES],
)
def test_given_invalid_load_selectors_when_running_load_then_it_raises_clear_error(
    test_case: LoadCommandSelectionErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    with pytest.raises(CliUserError) as exc_info:
        run_load(
            project_dir=tmp_path,
            no_color=True,
            select=test_case.select,
            exclude=test_case.exclude,
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    EMPTY_SELECTION_TEST_CASES,
    ids=[case.description for case in EMPTY_SELECTION_TEST_CASES],
)
def test_given_no_selected_managed_sources_when_running_load_then_it_does_not_connect(
    test_case: LoadCommandEmptySelectionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    capsys: CaptureFixture[str],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    exit_code: int = run_load(
        project_dir=tmp_path,
        no_color=True,
        select=test_case.select,
        exclude=test_case.exclude,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stdout_fragment in captured.out
    assert all(fragment in captured.out for fragment in test_case.expected_stdout_fragments)
    assert not (tmp_path / "demo.duckdb").exists()
