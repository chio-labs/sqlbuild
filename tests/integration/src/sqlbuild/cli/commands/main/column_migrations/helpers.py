"""Project builders and CLI runners for column migration integration tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.executor.build._helpers import scheduler as scheduler_module
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    execute,
    query,
    write_project,
)

MODEL_NAME: str = "fct_orders"
REPLAY_FULL: str = "  replay_on_change full,\n"
RELATION: str = f"main.{MODEL_NAME}"
_INCREMENTAL_HEADER: str = (
    "MODEL (\n"
    "  materialized incremental,\n"
    "  incremental_strategy {strategy},\n"
    "  unique_key order_id,\n"
    "  cursor {cursor},\n"
    "  cursor_type timestamp,\n"
    "  cursor_grain day,\n"
    '  cursor_start "2026-01-01",\n'
    "{extra_config}"
    ");\n\n"
)
_SNAPSHOT_HEADER: str = (
    "MODEL (\n"
    "  materialized snapshot,\n"
    "  unique_key [order_id],\n"
    "  snapshot_strategy timestamp,\n"
    "  updated_at order_date,\n"
    "{extra_config}"
    ");\n\n"
)


@dataclass(frozen=True)
class CliRun:
    """Captured result of one in-process sqb invocation."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        """Return stdout followed by stderr."""

        return self.stdout + self.stderr


def orders_sql(
    *,
    columns: str = "amount",
    extra_config: str = "",
    strategy: str = "delete_insert",
    cursor: str = "order_date",
    order_date: str = "order_date",
) -> str:
    """Return an incremental orders model projecting the given value columns."""

    return (
        _INCREMENTAL_HEADER.format(strategy=strategy, cursor=cursor, extra_config=extra_config)
        + f'SELECT order_id, {order_date}, {columns} FROM __source("raw_orders")\n'
    )


MICROBATCH_CONFIG: str = (
    "  incremental_mode microbatch,\n"
    "  microbatch_strategy watermark,\n"
    "  cursor_watermark_mode all,\n"
    "  batch_size 1d,\n"
    "  cursor_inputs (raw_orders (column order_date, roles [filter, watermark])),\n"
)


def state_table_names(*, project_dir: Path) -> tuple[str, ...]:
    """Return the SQLBuild state tables in the main schema."""

    return tuple(
        str(row[0])
        for row in query(
            project_dir=project_dir,
            sql=(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' "
                "AND starts_with(table_name, '_sqlbuild_') ORDER BY 1"
            ),
        )
    )


def snapshot_sql(*, columns: str = "amount", extra_config: str = "") -> str:
    """Return a timestamp snapshot of raw orders projecting the given value columns."""

    return (
        _SNAPSHOT_HEADER.format(extra_config=extra_config)
        + f'SELECT order_id, order_date, {columns} FROM __source("raw_orders")\n'
    )


def build_initial(
    *, project_dir: Path, capsys: pytest.CaptureFixture[str], sql: str | None = None
) -> None:
    """Build the orders model over three days, then load five days of raw orders."""

    write_model(project_dir=project_dir, sql=sql or orders_sql(extra_config=REPLAY_FULL))
    load_orders(project_dir=project_dir, last_day=3)
    _ = build_ok(project_dir=project_dir, capsys=capsys)
    load_orders(project_dir=project_dir, last_day=5)


def last_visible_line(output: str) -> str:
    """Return the final non-blank line of command output."""

    return output.rstrip().splitlines()[-1]


def migrate_columns(declarations: str) -> str:
    """Return a MODEL header columns block declaring column migrations."""

    return f"  columns ({declarations}),\n"


def write_model(*, project_dir: Path, sql: str) -> None:
    """Replace the project with exactly the orders model."""

    write_project(project_dir=project_dir, models={MODEL_NAME: sql})


def load_orders(*, project_dir: Path, last_day: int, failing_day: int | None = None) -> None:
    """Replace raw orders with one order per January day, optionally failing on one day."""

    amount: str = {None: "100 + i"}.get(
        failing_day, f"CASE WHEN i = {failing_day} THEN CAST('broken' AS BIGINT) ELSE 100 + i END"
    )
    execute(project_dir=project_dir, sql="DROP VIEW IF EXISTS main.raw_orders")
    execute(project_dir=project_dir, sql="DROP TABLE IF EXISTS main.raw_orders")
    execute(
        project_dir=project_dir,
        sql=(
            "CREATE VIEW main.raw_orders AS SELECT i AS order_id, "
            "TIMESTAMP '2026-01-01' + to_days(CAST(i - 1 AS INTEGER)) AS order_date, "
            f"{amount} AS amount, i AS tax "
            f"FROM range(1, {last_day + 1}) AS t(i)"
        ),
    )


def run_sqb(
    *, project_dir: Path, args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> CliRun:
    """Run sqb in-process and capture stdout and stderr separately."""

    _ = capsys.readouterr()
    try:
        exit_code: int = main(["--project-dir", str(project_dir), "--no-color", *args])
    except Exception as error:
        captured_error: CaptureResult[str] = capsys.readouterr()
        return CliRun(exit_code=1, stdout=captured_error.out, stderr=str(error))
    captured: CaptureResult[str] = capsys.readouterr()
    return CliRun(exit_code=exit_code, stdout=captured.out, stderr=captured.err)


def build(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> CliRun:
    """Run sqb build."""

    return run_sqb(project_dir=project_dir, args=("build",), capsys=capsys)


def build_ok(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> CliRun:
    """Run sqb build and require success."""

    result: CliRun = build(project_dir=project_dir, capsys=capsys)
    assert result.exit_code == 0, result.output
    return result


def plan_text(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """Run sqb plan and return its text output."""

    result: CliRun = run_sqb(project_dir=project_dir, args=("plan",), capsys=capsys)
    assert result.exit_code == 0, result.output
    return result.stdout


def plan_json(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """Run sqb plan --json and parse stdout."""

    result: CliRun = run_sqb(project_dir=project_dir, args=("plan", "--json"), capsys=capsys)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def planned_column_migrations(plan: dict[str, Any]) -> tuple[tuple[str, str, str, str], ...]:
    """Return (origin, destination, discovery, decision) for every planned column migration."""

    return tuple(
        (
            str(entry["origin_column"]),
            str(entry["destination_column"]),
            str(entry["discovery"]),
            str(entry["decision"]),
        )
        for entry in plan["column_migrations"]
    )


def model_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return the serialized plan entry of the orders model."""

    return {model["name"]: model for model in plan["models"]}[MODEL_NAME]


def warning_codes(plan: dict[str, Any]) -> tuple[str, ...]:
    """Return every plan warning code in order."""

    return tuple(str(warning.get("code")) for warning in plan["warnings"])


def column_names(*, project_dir: Path, relation: str = RELATION) -> tuple[str, ...]:
    """Return the physical column names of one relation in order."""

    schema: str
    name: str
    schema, name = relation.split(".")
    return tuple(
        str(row[0])
        for row in query(
            project_dir=project_dir,
            sql=(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_schema = '{schema}' AND table_name = '{name}' "
                "ORDER BY ordinal_position"
            ),
        )
    )


def column_values(
    *, project_dir: Path, column: str, relation: str = RELATION
) -> tuple[tuple[int, Any], ...]:
    """Return (order_id, value) for every row of one relation in order."""

    return tuple(
        (int(row[0]), row[1])
        for row in query(
            project_dir=project_dir,
            sql=f"SELECT order_id, {column} FROM {relation} ORDER BY order_id, {column}",
        )
    )


def column_events(*, project_dir: Path) -> tuple[tuple[str, str, str, str], ...]:
    """Return (origin, destination, discovery, decision) for every recorded column rename."""

    return tuple(
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
        for row in query(
            project_dir=project_dir,
            sql=(
                "SELECT origin_column, destination_column, discovery, decision "
                "FROM main._sqlbuild_column_migrations ORDER BY created_at, event_id"
            ),
        )
    )


def change_historical_amount(*, project_dir: Path) -> None:
    """Change day one's raw amount so any replay would be visible in built history."""

    execute(
        project_dir=project_dir,
        sql=(
            "CREATE OR REPLACE VIEW main.raw_orders AS SELECT order_id, order_date, "
            "CASE WHEN order_id = 1 THEN 999 ELSE amount END AS amount, tax "
            "FROM (SELECT i AS order_id, "
            "TIMESTAMP '2026-01-01' + to_days(CAST(i - 1 AS INTEGER)) AS order_date, "
            "100 + i AS amount, i AS tax FROM range(1, 6) AS t(i))"
        ),
    )


def _raise_interruption(*_: object, **__: object) -> None:
    raise RuntimeError("simulated interruption")


def fail_model_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the orders model's incremental build raise after column migrations have run."""

    incremental: Callable[..., Any] = scheduler_module.execute_incremental_entry
    failing: dict[str, Callable[..., Any]] = {MODEL_NAME: _raise_interruption}
    monkeypatch.setattr(
        scheduler_module,
        "execute_incremental_entry",
        lambda **kwargs: failing.get(kwargs["context"].entry.name, incremental)(**kwargs),
    )


def fail_non_transactional_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rename without a transaction, then crash before the event is recorded."""

    monkeypatch.setattr(DuckDbAdapter, "supports_transactional_ddl", lambda self: False)
    monkeypatch.setattr(
        "sqlbuild.executor.migrations._helpers.columns.write_column_migration_event",
        _raise_interruption,
    )
