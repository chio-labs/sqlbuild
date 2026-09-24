"""Project builders and CLI runners for model migration integration tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

import duckdb
import pytest
from _pytest.capture import CaptureResult

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
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
VIRTUAL_PROJECT_TOML: str = dedent(
    f"""
    name = "orders_project"
    adapter = "duckdb"
    default_target = "dev"

    [settings]
    virtual_environments = true

    [connection]
    database = "{DATABASE_FILE}"

    [targets.dev]
    schema = "dev"

    [targets.dev.state]
    backend = "duckdb"
    schema = "sqlbuild_state"

    [targets.dev.state.connection]
    database = "state.duckdb"
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


_FORCE_LINES: dict[bool, str] = {True: "  migrate_force true,\n", False: ""}
_DAILY_TOTALS_HEADER: str = (
    "MODEL (\n"
    "  materialized incremental,\n"
    "  incremental_strategy delete_insert,\n"
    "  unique_key order_date,\n"
    "  cursor order_date,\n"
    "  cursor_type timestamp,\n"
    "  cursor_grain day,\n"
    '  cursor_start "2026-01-01",\n'
    ");\n\n"
)
_SNAPSHOT_SQL: str = (
    "MODEL (\n"
    "  materialized snapshot,\n"
    "  unique_key [order_id],\n"
    "  snapshot_strategy timestamp,\n"
    "  updated_at order_date,\n"
    "{migration}"
    ");\n\n"
    'SELECT order_id, order_date, amount_cents FROM __source("raw_orders")\n'
)
ORIGIN_MODEL: str = "stg_orders"
DESTINATION_MODEL: str = "stg_customer_orders"


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

    origin_lines: dict[str | None, str] = {None: ""}
    migration_lines: str = origin_lines.get(
        migrate_from, f'  migrate_from "{migrate_from}",\n'
    ) + _FORCE_LINES.get(migrate_force, "")
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


def order_ids(*, project_dir: Path, relation: str) -> tuple[int, ...]:
    """Return the sorted order IDs stored in one relation."""

    return tuple(
        int(row[0])
        for row in query(project_dir=project_dir, sql=f"SELECT order_id FROM {relation} ORDER BY 1")
    )


def migration_events(
    *, project_dir: Path, schema: str = "main"
) -> tuple[tuple[str, str, str], ...]:
    """Return (origin, destination, decision) for every recorded event in creation order."""

    return tuple(
        (str(row[0]), str(row[1]), str(row[2]))
        for row in query(
            project_dir=project_dir,
            sql=(
                "SELECT origin_name, destination_name, decision "
                f"FROM {schema}._sqlbuild_migrations ORDER BY created_at, event_id"
            ),
        )
    )


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
    captured: CaptureResult[str] = capsys.readouterr()
    return CliRun(exit_code=exit_code, output=captured.out + captured.err)


def build(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> CliRun:
    """Run sqb build, reporting an escaped exception as a failed run."""

    try:
        return run_sqb(project_dir=project_dir, args=("build",), capsys=capsys)
    except Exception as error:
        return CliRun(exit_code=1, output=str(error))


def build_ok(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> CliRun:
    """Run sqb build and require success."""

    result: CliRun = build(project_dir=project_dir, capsys=capsys)
    assert result.exit_code == 0, result.output
    return result


def plan_json(
    *, project_dir: Path, capsys: pytest.CaptureFixture[str], args: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Run sqb plan --json and parse stdout."""

    _ = capsys.readouterr()
    exit_code: int = main(
        ["--project-dir", str(project_dir), "--no-color", "plan", "--json", *args]
    )
    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0, captured.out + captured.err
    return json.loads(captured.out)


def model_entry(*, plan: dict[str, Any], name: str) -> dict[str, Any]:
    """Return one serialized model entry from plan JSON."""

    models_by_name: dict[str, dict[str, Any]] = {model["name"]: model for model in plan["models"]}
    return models_by_name[name]


def migration_decisions(plan: dict[str, Any]) -> tuple[str, ...]:
    """Return every planned migration decision in plan order."""

    return tuple(migration["decision"] for migration in plan["migrations"])


def planned_migrations(plan: dict[str, Any]) -> tuple[tuple[str | None, str, str, str], ...]:
    """Return sorted (origin, destination, discovery, decision) for every planned migration."""

    return tuple(
        sorted(
            (
                migration["origin_model"],
                migration["model"],
                migration["discovery"],
                migration["decision"],
            )
            for migration in plan["migrations"]
        )
    )


def warning_messages(plan: dict[str, Any]) -> tuple[str, ...]:
    """Return every plan warning message."""

    return tuple(str(warning["message"]) for warning in plan["warnings"])


def row_count(*, project_dir: Path, relation: str) -> int:
    """Return the number of rows stored in one relation."""

    return int(query(project_dir=project_dir, sql=f"SELECT count(*) FROM {relation}")[0][0])


def build_origin(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Build the origin orders model over five days of raw orders."""

    write_project(project_dir=project_dir, models={ORIGIN_MODEL: incremental_orders_sql()})
    load_raw_orders(project_dir=project_dir, first_day=1, last_day=5)
    _ = build_ok(project_dir=project_dir, capsys=capsys)


def rename_model(
    *,
    project_dir: Path,
    name: str,
    migrate_from: str | None,
    migrate_force: bool = False,
    extra_config: str = "",
) -> None:
    """Replace the project with one incremental orders model under a new name."""

    write_project(
        project_dir=project_dir,
        models={
            name: incremental_orders_sql(
                migrate_from=migrate_from, migrate_force=migrate_force, extra_config=extra_config
            )
        },
    )


def snapshot_orders_sql(*, migration_lines: str) -> str:
    """Return a timestamp snapshot of raw orders with optional migration header lines."""

    return _SNAPSHOT_SQL.format(migration=migration_lines)


def _raise_interruption(**_: object) -> None:
    raise RuntimeError("simulated interruption")


def fail_clone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the migration clone statement fail."""

    monkeypatch.setattr(
        DuckDbAdapter,
        "render_replace_with_clone",
        lambda self, *, origin, destination, origin_is_transient=False: (
            "SELECT * FROM main.simulated_missing_relation"
        ),
    )


def fail_clone_into(*, monkeypatch: pytest.MonkeyPatch, destination: str) -> None:
    """Make only the clone into one destination fail; every other clone runs normally."""

    original: Callable[..., str] = DuckDbAdapter.render_replace_with_clone
    failing: dict[str, str] = {destination: "SELECT * FROM main.simulated_missing_relation"}
    monkeypatch.setattr(
        DuckDbAdapter,
        "render_replace_with_clone",
        lambda self, *, origin, destination, origin_is_transient=False: failing.get(
            destination,
            original(
                self,
                origin=origin,
                destination=destination,
                origin_is_transient=origin_is_transient,
            ),
        ),
    )


def fail_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash after the clone but before the migration event is recorded."""

    monkeypatch.setattr(
        "sqlbuild.executor.build.main._apply_model_migrations.write_migration_event",
        _raise_interruption,
    )


def fail_after_migrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash after migrations are recorded but before any model builds."""

    monkeypatch.setattr(
        "sqlbuild.executor.build.main._execute.apply_retention_phase", _raise_interruption
    )


def enriched_view_sql(*, upstream: str, alias: str) -> str:
    """Return a view that selects every order column through a table alias."""

    return (
        "MODEL (materialized view);\n\n"
        f"SELECT {alias}.order_id, {alias}.order_date, {alias}.amount_cents "
        f'FROM __ref("{upstream}") AS {alias}\n'
    )


def daily_totals_sql(*, upstream: str, cte: str, comment: str = "") -> str:
    """Return an incremental daily revenue model that imports its upstream through a CTE."""

    return (
        f"{_DAILY_TOTALS_HEADER}"
        f"{comment}"
        f'WITH {cte} AS (SELECT * FROM __ref("{upstream}"))\n'
        f"SELECT\n    {cte}.order_date,\n    SUM({cte}.amount_cents) AS total_cents\n"
        f"FROM {cte}\nGROUP BY {cte}.order_date\n"
    )


def original_order_models() -> dict[str, str]:
    """Return the connected staging, view, and daily totals models before renaming."""

    return {
        "stg_orders": incremental_orders_sql(),
        "orders_enriched": enriched_view_sql(upstream="stg_orders", alias="o"),
        "daily_order_totals": daily_totals_sql(upstream="orders_enriched", cte="orders_enriched"),
    }


def renamed_order_models() -> dict[str, str]:
    """Return the same connected models renamed, reformatted, and with new storage settings."""

    return {
        "stg_customer_orders": incremental_orders_sql(extra_config="  lookback 1d,\n"),
        "customer_orders_enriched": enriched_view_sql(
            upstream="stg_customer_orders", alias="customer_order"
        ),
        "customer_daily_order_totals": daily_totals_sql(
            upstream="customer_orders_enriched",
            cte="customer_orders_enriched",
            comment="-- Daily revenue per order date.\n",
        ),
    }


def build_original_order_models(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Build the connected models over five days of raw orders."""

    write_project(project_dir=project_dir, models=original_order_models())
    load_raw_orders(project_dir=project_dir, first_day=1, last_day=5)
    _ = build_ok(project_dir=project_dir, capsys=capsys)


def warehouse_state(*, project_dir: Path) -> tuple[tuple[Any, ...], ...]:
    """Return (schema, relation, row count) for every relation in the dev and prod schemas."""

    tables: list[tuple[Any, ...]] = query(
        project_dir=project_dir,
        sql=(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('dev', 'prod') ORDER BY 1, 2"
        ),
    )
    return tuple(
        (schema, name, row_count(project_dir=project_dir, relation=f"{schema}.{name}"))
        for schema, name in tables
    )


def prepare_prod_rename(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Build the origin on prod, then rename it with migrate_from in the project."""

    write_project(
        project_dir=project_dir,
        models={ORIGIN_MODEL: incremental_orders_sql()},
        project_toml=TARGETS_PROJECT_TOML,
    )
    load_raw_orders(project_dir=project_dir, first_day=1, last_day=4)
    built: CliRun = run_sqb(
        project_dir=project_dir, args=("build", "--target", "prod"), capsys=capsys
    )
    assert built.exit_code == 0, built.output
    write_project(
        project_dir=project_dir,
        models={DESTINATION_MODEL: incremental_orders_sql(migrate_from=ORIGIN_MODEL)},
        project_toml=TARGETS_PROJECT_TOML,
    )
