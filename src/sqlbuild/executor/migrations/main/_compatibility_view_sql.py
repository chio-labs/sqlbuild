"""Render the SQL a recorded compatibility view is defined by."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.migrations.models import MigrationRelation, OldNameViewHistory
from sqlbuild.executor.migrations._helpers.old_name_views import render_old_name_view_select
from sqlbuild.executor.migrations.models import OldNameViewSource


def compatibility_view_sql(
    *, adapter: BaseAdapter, connection: Any, history: OldNameViewHistory
) -> tuple[str, ...]:
    """Return the SQL the view was created from and the SQL a build would redefine it with."""

    recorded: str | None = None if history.created is None else history.created.view_sql
    aliases: tuple[tuple[str, str], ...] = (
        () if history.created is None else history.created.column_aliases
    )
    new: CompiledRelationLocation = _location(adapter=adapter, relation=history.new)
    if adapter.views_bind_to_relation_identity() and not adapter.list_relations(
        connection=connection,
        database=new.database,
        schemas=(new.schema or "",),
        names=(new.name,),
    ):
        return ()
    rendered: tuple[str, ...] = ()
    if not aliases or adapter.get_columns(
        connection=connection, database=new.database, schema=new.schema, name=new.name
    ):
        rendered = (
            render_old_name_view_select(
                adapter=adapter,
                connection=connection,
                source=OldNameViewSource(
                    old=_location(adapter=adapter, relation=history.old),
                    new=new,
                    column_aliases=aliases,
                ),
            ),
        )
    return tuple(dict.fromkeys((*rendered, *(() if recorded is None else (recorded,)))))


def _location(*, adapter: BaseAdapter, relation: MigrationRelation) -> CompiledRelationLocation:
    return CompiledRelationLocation(
        database=relation.database,
        schema=relation.schema,
        name=relation.name,
        qualified_name=adapter.render_qualified_name(
            database=relation.database, schema=relation.schema, name=relation.name
        ),
    )
