"""Project builders and fault injection for old-name compatibility view integration tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from sqlbuild.compiler.migrations.models import OldNameViewEvent
from sqlbuild.compiler.migrations.types import OldNameViewEventType
from sqlbuild.executor.migrations._helpers import old_name_views as old_name_steps
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    CliRun,
    build_ok,
    disable_transactional_ddl,
    load_raw_orders,
    query,
    write_project,
)

ORIGIN_MODEL: str = "revenue"
DESTINATION_MODEL: str = "daily_revenue"
PROJECT_TOML: str = dedent(
    """
    name = "orders_project"
    adapter = "duckdb"

    [connection]
    database = "orders.duckdb"
    """
).lstrip()
_FACT_ORDER: tuple[str, ...] = ("required", "origin_archived", "view_created", "view_dropped")
_TABLE_SQL: str = (
    "MODEL (materialized table{extra});\n"
    'SELECT order_id, amount_cents FROM __source("raw_orders")\n'
)


def table_sql(*, migrate_from: str | None = None) -> str:
    """Return a table model over raw orders with an optional migrate_from header."""

    extra: str = {None: ""}.get(migrate_from, f", migrate_from {migrate_from}")
    return _TABLE_SQL.format(extra=extra)


def prepare_table_rename(
    *, project_dir: Path, capsys: pytest.CaptureFixture[str], project_toml: str = PROJECT_TOML
) -> None:
    """Build the origin table, then declare its rename to the destination."""

    write_project(
        project_dir=project_dir, models={ORIGIN_MODEL: table_sql()}, project_toml=project_toml
    )
    load_raw_orders(project_dir=project_dir, first_day=1, last_day=3)
    _ = build_ok(project_dir=project_dir, capsys=capsys)
    write_project(
        project_dir=project_dir,
        models={DESTINATION_MODEL: table_sql(migrate_from=ORIGIN_MODEL)},
        project_toml=project_toml,
    )


def old_name_facts(*, project_dir: Path, schema: str = "main") -> tuple[str, ...]:
    """Return recorded old-name fact types in lifecycle order."""

    return tuple(
        str(row[0])
        for row in query(
            project_dir=project_dir,
            sql=(
                f"SELECT event_type FROM {schema}._sqlbuild_old_name_views ORDER BY "
                f"list_position({list(_FACT_ORDER)}, event_type), created_at"
            ),
        )
    )


def relation_type(*, project_dir: Path, name: str) -> str | None:
    """Return the information_schema type of one relation in main, or None."""

    rows: list[tuple[Any, ...]] = query(
        project_dir=project_dir,
        sql=(
            "SELECT table_type FROM information_schema.tables "
            f"WHERE table_schema = 'main' AND table_name = '{name}'"
        ),
    )
    return next((str(row[0]) for row in rows), None)


def origin_archive_count(*, project_dir: Path) -> int:
    """Return how many migration_origin archives exist in main."""

    return int(
        query(
            project_dir=project_dir,
            sql=(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'main' "
                "AND contains(table_name, '__migration_origin__')"
            ),
        )[0][0]
    )


def _raise_interruption(*_: object, **__: object) -> None:
    raise RuntimeError("simulated interruption")


def _fail_fact(*, monkeypatch: pytest.MonkeyPatch, event_type: OldNameViewEventType) -> None:
    original: Callable[..., None] = old_name_steps.record_old_name_fact

    outcomes: dict[bool, Callable[..., None]] = {True: _raise_interruption, False: original}

    def failing(*, event: OldNameViewEvent, **kwargs: Any) -> None:
        outcomes[event.event_type == event_type](event=event, **kwargs)

    monkeypatch.setattr(old_name_steps, "record_old_name_fact", failing)


def fail_destination_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the destination table build after its move is recorded."""

    from sqlbuild.executor.build._helpers import scheduler as scheduler_module

    original: Callable[..., Any] = scheduler_module.execute_table_entry
    failing: dict[str, Callable[..., Any]] = {DESTINATION_MODEL: _raise_interruption}
    monkeypatch.setattr(
        scheduler_module,
        "execute_table_entry",
        lambda **kwargs: failing.get(kwargs["context"].entry.name, original)(**kwargs),
    )


def fail_transactional_view(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail creating the view inside the archive-and-view transaction."""

    monkeypatch.setattr(old_name_steps, "_create_compatibility_view", _raise_interruption)


def fail_non_transactional_archive_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash after the old relation is renamed but before its archive is recorded."""

    disable_transactional_ddl(monkeypatch)
    _fail_fact(monkeypatch=monkeypatch, event_type=OldNameViewEventType.ORIGIN_ARCHIVED)


def fail_non_transactional_view(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash after the archive is recorded but before the view exists."""

    disable_transactional_ddl(monkeypatch)
    monkeypatch.setattr(old_name_steps, "_create_compatibility_view", _raise_interruption)


def fail_non_transactional_view_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash after the view is created but before it is recorded."""

    disable_transactional_ddl(monkeypatch)
    _fail_fact(monkeypatch=monkeypatch, event_type=OldNameViewEventType.VIEW_CREATED)


def build_result(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> CliRun:
    """Run sqb build, reporting an escaped exception as a failed run."""

    from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import build

    return build(project_dir=project_dir, capsys=capsys)


JANITOR_PROJECT_TOML: str = dedent(
    """
    name = "orders_project"
    adapter = "duckdb"
    default_target = "dev"

    [connection]
    database = "orders.duckdb"

    [targets.dev]
    schema = "dev"

    [janitor]
    enabled = true
    """
).lstrip()


def fail_janitor_drop_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash after the janitor drops a view but before the drop is recorded."""

    monkeypatch.setattr(
        "sqlbuild.executor.old_name_views._helpers.janitor.write_old_name_view_event",
        _raise_interruption,
    )


def disabled_table_sql(*, migrate_from: str) -> str:
    """Return a table model that declares its rename with old-name views turned off."""

    return (
        f"MODEL (materialized table, migrate_from {migrate_from}, old_name_view false);\n"
        'SELECT order_id, amount_cents FROM __source("raw_orders")\n'
    )


def plan_text(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """Run sqb plan and return its text output."""

    from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import run_sqb

    return run_sqb(project_dir=project_dir, args=("plan",), capsys=capsys).output
