"""Project builders and CLI runners for model migration integration tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

import duckdb
import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main

DATABASE_FILE: str = "orders.duckdb"
PROJECT_TOML: str = dedent(
    f"""
    name = "orders_project"
    adapter = "duckdb"

    [connection]
    database = "{DATABASE_FILE}"
    """
).lstrip()
TARGETS_PROJECT_TOML: str = dedent(
    f"""
    name = "orders_project"
    adapter = "duckdb"
    default_target = "dev"

    [connection]
    database = "{DATABASE_FILE}"

    [targets.dev]
    schema = "dev"

    [targets.prod]
    schema = "prod"
    """
).lstrip()
RAW_SOURCES_YML: str = dedent(
    """
    sources:
      - name: raw_orders
        schema: main
        table: raw_orders
    """
).lstrip()


@dataclass(frozen=True)
class CliRun:
    """Captured result of one in-process sqb invocation."""

    exit_code: int
    output: str


def incremental_orders_sql(
    *,
    migrate_from: str | None = None,
    migrate_force: bool = False,
    extra_config: str = "",
    select_sql: str = 'SELECT order_id, order_date, amount_cents FROM __source("raw_orders")',
) -> str:
    """Return an incremental orders model with optional migration header keys."""

    migration_lines: str = ""
    if migrate_from is not None:
        migration_lines += f'  migrate_from "{migrate_from}",\n'
    if migrate_force:
        migration_lines += "  migrate_force true,\n"
    return (
        "MODEL (\n"
        "  materialized incremental,\n"
        "  incremental_strategy delete_insert,\n"
        "  unique_key order_id,\n"
        "  cursor order_date,\n"
        "  cursor_type timestamp,\n"
        "  cursor_grain day,\n"
        '  cursor_start "2026-01-01",\n'
        f"{extra_config}"
        f"{migration_lines}"
        ");\n\n"
        f"{select_sql}\n"
    )


def write_project(
    *, project_dir: Path, models: dict[str, str], project_toml: str = PROJECT_TOML
) -> None:
    """Write the project config, sources, and exactly the given model files."""

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sqlbuild_project.toml").write_text(project_toml, encoding="utf-8")
    sources_dir: Path = project_dir / "sources"
    sources_dir.mkdir(exist_ok=True)
    (sources_dir / "raw.yml").write_text(RAW_SOURCES_YML, encoding="utf-8")
    models_dir: Path = project_dir / "models"
    models_dir.mkdir(exist_ok=True)
    existing: Path
    for existing in models_dir.glob("*.sql"):
        existing.unlink()
    name: str
    sql: str
    for name, sql in models.items():
        (models_dir / f"{name}.sql").write_text(sql, encoding="utf-8")


def load_raw_orders(*, project_dir: Path, first_day: int, last_day: int) -> None:
    """Replace raw orders with one order per day in the inclusive January day range."""

    execute(
        project_dir=project_dir,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_orders AS SELECT i AS order_id, "
            "TIMESTAMP '2026-01-01' + to_days(CAST(i - 1 AS INTEGER)) AS order_date, "
            "100 + i AS amount_cents "
            f"FROM range({first_day}, {last_day + 1}) AS t(i)"
        ),
    )


def execute(*, project_dir: Path, sql: str) -> None:
    """Run one mutating statement against the project database."""

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(project_dir / DATABASE_FILE))
    try:
        _ = connection.execute(sql)
    finally:
        connection.close()


def query(*, project_dir: Path, sql: str) -> list[tuple[Any, ...]]:
    """Read rows from the project database."""

    connection: duckdb.DuckDBPyConnection = duckdb.connect(
        str(project_dir / DATABASE_FILE), read_only=True
    )
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def order_ids(*, project_dir: Path, relation: str) -> list[int]:
    """Return the sorted order IDs stored in one relation."""

    return [
        int(row[0])
        for row in query(project_dir=project_dir, sql=f"SELECT order_id FROM {relation} ORDER BY 1")
    ]


def migration_events(*, project_dir: Path, schema: str = "main") -> list[tuple[str, str, str]]:
    """Return (origin, destination, decision) for every recorded event in creation order."""

    return [
        (str(row[0]), str(row[1]), str(row[2]))
        for row in query(
            project_dir=project_dir,
            sql=(
                "SELECT origin_name, destination_name, decision "
                f"FROM {schema}._sqlbuild_migrations ORDER BY created_at, event_id"
            ),
        )
    ]


def relation_names(*, project_dir: Path, schema: str) -> list[str]:
    """Return every relation name in one schema."""

    return [
        str(row[0])
        for row in query(
            project_dir=project_dir,
            sql=(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = '{schema}' ORDER BY 1"
            ),
        )
    ]


def run_sqb(
    *, project_dir: Path, args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> CliRun:
    """Run sqb in-process and capture combined output."""

    _ = capsys.readouterr()
    exit_code: int = main(["--project-dir", str(project_dir), "--no-color", *args])
    captured: pytest.CaptureResult[str] = capsys.readouterr()
    return CliRun(exit_code=exit_code, output=captured.out + captured.err)


def plan_json(
    *, project_dir: Path, capsys: pytest.CaptureFixture[str], args: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Run sqb plan --json and parse stdout."""

    _ = capsys.readouterr()
    exit_code: int = main(["--project-dir", str(project_dir), "--no-color", "plan", "--json", *args])
    captured: pytest.CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0, captured.out + captured.err
    return json.loads(captured.out)


def model_entry(*, plan: dict[str, Any], name: str) -> dict[str, Any]:
    """Return one serialized model entry from plan JSON."""

    return next(model for model in plan["models"] if model["name"] == name)
