"""Follow Snowflake view dependencies from in-use candidates to the candidates behind them."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsage
from sqlbuild.adapters.snowflake.constants import (
    DEPENDENCY_VIEW_DOMAINS,
    QUOTED_IDENTIFIER_MARK,
    USAGE_NAME_CHUNK_SIZE,
)
from sqlbuild.adapters.snowflake.models import UsageQuery


def dependency_name(*, relation: RelationInfo, current_database: str | None) -> str | None:
    """The `DATABASE.SCHEMA.NAME` OBJECT_DEPENDENCIES records for an unquoted relation."""

    database: str | None = relation.database or current_database
    if database is None or relation.schema is None:
        return None
    return ".".join(part.upper() for part in (database, relation.schema, relation.name))


def display_name(object_name: str) -> str:
    """A Snowflake object name as SQLBuild prints it: unquoted names in lowercase."""

    return object_name if QUOTED_IDENTIFIER_MARK in object_name else object_name.lower()


def dependency_queries(*, view_names: Iterable[str]) -> tuple[UsageQuery, ...]:
    """One OBJECT_DEPENDENCIES read per chunk of candidate views."""

    names: tuple[str, ...] = tuple(sorted(view_names))
    return tuple(
        dependency_query(view_names=names[start : start + USAGE_NAME_CHUNK_SIZE])
        for start in range(0, len(names), USAGE_NAME_CHUNK_SIZE)
    )


def dependency_query(*, view_names: tuple[str, ...]) -> UsageQuery:
    """What each named view references, as `(referencing, referenced)` dotted names."""

    placeholders: str = ", ".join(["%s"] * len(view_names))
    domains: str = ", ".join(["%s"] * len(DEPENDENCY_VIEW_DOMAINS))
    referencing: str = (
        "referencing_database || '.' || referencing_schema || '.' || referencing_object_name"
    )
    sql: str = (
        f"SELECT {referencing} AS referencing_name, "
        "referenced_database || '.' || referenced_schema || '.' || referenced_object_name "
        "AS referenced_name "
        "FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES "
        f"WHERE referencing_object_domain IN ({domains}) "
        f"AND {referencing} IN ({placeholders}) "
        "ORDER BY 1, 2"
    )
    return UsageQuery(sql=sql, params=(*DEPENDENCY_VIEW_DOMAINS, *view_names))


def _folded(relation: RelationInfo | RelationUsage) -> tuple[str, str, str]:
    return (
        (relation.database or "").lower(),
        (relation.schema or "").lower(),
        relation.name.lower(),
    )


def _via_parent(
    *,
    relation: RelationInfo,
    parent: str,
    parent_usage: RelationUsage,
    earlier: RelationUsage | None,
) -> RelationUsage:
    via: tuple[str, ...] = (display_name(parent),)
    readers: tuple[str, ...] = parent_usage.readers
    last_read_at: datetime = parent_usage.last_read_at
    query_count: int = parent_usage.query_count
    if earlier is not None:
        via = tuple(sorted({*earlier.via, *via}))
        readers = tuple(dict.fromkeys((*earlier.readers, *readers)))
        last_read_at = max(earlier.last_read_at, last_read_at)
        query_count = max(earlier.query_count, query_count)
    return RelationUsage(
        database=relation.database,
        schema=relation.schema,
        name=relation.name,
        last_read_at=last_read_at,
        readers=readers,
        query_count=query_count,
        direct=False,
        via=via,
    )


def chained_usages(
    *,
    usages: tuple[RelationUsage, ...],
    dependencies: Iterable[tuple[str, str]],
    relations_by_dependency_name: Mapping[str, RelationInfo],
) -> tuple[RelationUsage, ...]:
    """Usages plus every candidate an in-use candidate view depends on, transitively."""

    references: dict[str, set[str]] = {}
    referencing: str
    referenced: str
    for referencing, referenced in dependencies:
        if referenced in relations_by_dependency_name:
            references.setdefault(referencing, set()).add(referenced)
    names_by_key: dict[tuple[str, str, str], str] = {
        _folded(relation): name for name, relation in relations_by_dependency_name.items()
    }
    read: dict[str, RelationUsage] = {
        names_by_key[_folded(usage)]: usage for usage in usages if _folded(usage) in names_by_key
    }
    found: dict[str, RelationUsage] = {}
    pending: list[str] = sorted(read)
    while pending:
        parent: str = pending.pop(0)
        parent_usage: RelationUsage = read.get(parent) or found[parent]
        child: str
        for child in sorted(references.get(parent, ())):
            if child in read:
                continue
            earlier: RelationUsage | None = found.get(child)
            found[child] = _via_parent(
                relation=relations_by_dependency_name[child],
                parent=parent,
                parent_usage=parent_usage,
                earlier=earlier,
            )
            if earlier is None:
                pending.append(child)
    return (*usages, *(found[name] for name in sorted(found)))
