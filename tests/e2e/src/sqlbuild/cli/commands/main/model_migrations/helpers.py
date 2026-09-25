"""Project builders for model migration CLI e2e tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)

DATABASE_FILE: str = "orders.duckdb"
_PROJECT_TOML: str = (
    f'name = "orders_project"\nadapter = "duckdb"\n\n[connection]\ndatabase = "{DATABASE_FILE}"\n'
)
_SOURCES_YML: str = "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"


def orders_sql(*, migrate_from: str) -> str:
    """Return an incremental orders model with an optional migrate_from header."""

    migration: str = {"": ""}.get(migrate_from, f'  migrate_from "{migrate_from}",\n')
    return (
        "MODEL (\n"
        "  materialized incremental,\n"
        "  incremental_strategy delete_insert,\n"
        "  unique_key order_id,\n"
        "  cursor order_date,\n"
        "  cursor_type timestamp,\n"
        "  cursor_grain day,\n"
        '  cursor_start "2026-01-01",\n'
        f"{migration}"
        ");\n\n"
        'SELECT order_id, order_date, amount_cents FROM __source("raw_orders")\n'
    )


def write_orders_project(*, tmp_path: Path, name: str, migrate_from: str) -> Path:
    """Write a project containing exactly one incremental orders model."""

    project_dir: Path = tmp_path / "orders_project"
    stale: Path
    for stale in (project_dir / "models").glob("*.sql"):
        stale.unlink()
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="orders_project",
        repo_files={
            "sqlbuild_project.toml": _PROJECT_TOML,
            "sources/raw.yml": _SOURCES_YML,
            f"models/{name}.sql": orders_sql(migrate_from=migrate_from),
        },
    )


def load_raw_orders(*, project_dir: Path, last_day: int) -> None:
    """Replace raw orders with one order per January day up to the given day."""

    execute_duckdb(
        db_path=project_dir / DATABASE_FILE,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_orders AS SELECT i AS order_id, "
            "TIMESTAMP '2026-01-01' + to_days(CAST(i - 1 AS INTEGER)) AS order_date, "
            f"100 + i AS amount_cents FROM range(1, {last_day + 1}) AS t(i)"
        ),
    )


def plan_decisions(*, project_dir: Path) -> tuple[str, ...]:
    """Run sqb plan --json in a subprocess and return the migration decisions."""

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--json"), project_dir=project_dir
    )
    payload: dict[str, Any] = json.loads(result.stdout)
    return tuple(str(migration["decision"]) for migration in payload["migrations"])


def build(*, project_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run sqb build in a subprocess."""

    return run_sqb(command=("--no-color", "build"), project_dir=project_dir)


def order_ids(*, project_dir: Path, relation: str) -> tuple[int, ...]:
    """Return the sorted order IDs stored in one relation."""

    return tuple(
        int(row[0])
        for row in query_duckdb(
            db_path=project_dir / DATABASE_FILE,
            sql=f"SELECT order_id FROM {relation} ORDER BY 1",
        )
    )


def previous_archive_ids(*, project_dir: Path) -> tuple[tuple[int, ...], ...]:
    """Return the order IDs held by each displaced-destination archive."""

    names: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / DATABASE_FILE,
        sql=(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' "
            "AND contains(table_name, '__migration_previous__') ORDER BY 1"
        ),
    )
    return tuple(order_ids(project_dir=project_dir, relation=f"main.{row[0]}") for row in names)


def migration_events(*, project_dir: Path) -> tuple[tuple[str, str, str], ...]:
    """Return (origin, destination, decision) for every recorded migration event in order."""

    return tuple(
        (str(row[0]), str(row[1]), str(row[2]))
        for row in query_duckdb(
            db_path=project_dir / DATABASE_FILE,
            sql=(
                "SELECT origin_name, destination_name, decision FROM main._sqlbuild_migrations "
                "ORDER BY created_at, event_id"
            ),
        )
    )
