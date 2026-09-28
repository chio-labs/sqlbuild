"""Read the old-name view history of every recorded move in one schema."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.migrations.main._project_old_name_views import project_old_name_views
from sqlbuild.compiler.migrations.main._read_events import read_migration_events
from sqlbuild.compiler.migrations.main.read_old_name_view_events import (
    read_old_name_view_events,
)
from sqlbuild.compiler.migrations.models import OldNameViewHistory


def read_old_name_view_histories(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    stored_columns: Iterable[str],
    render_qualified_name: Callable[..., str | None],
) -> tuple[OldNameViewHistory, ...]:
    """Read moves and old-name facts from a schema that holds both state tables."""

    return project_old_name_views(
        moves=read_migration_events(
            connection=connection,
            execute=execute,
            database=database,
            schema=schema,
            render_qualified_name=render_qualified_name,
        ),
        facts=read_old_name_view_events(
            connection=connection,
            execute=execute,
            database=database,
            schema=schema,
            stored_columns=stored_columns,
            render_qualified_name=render_qualified_name,
        ),
    )
