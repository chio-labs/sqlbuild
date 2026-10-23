"""Follow Snowflake view dependencies from directly read objects to the candidates behind them."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsage
from sqlbuild.adapters.snowflake.constants import (
    DEPENDENCY_VIEW_DOMAINS,
    NAME_SEPARATOR,
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


def dependency_key(object_name: str) -> str:
    """An access-history or printed object name as OBJECT_DEPENDENCIES spells it."""

    parts: list[str] = []
    current: list[str] = []
    quoted: bool = False
    was_quoted: bool = False
    index: int = 0
    while index < len(object_name):
        character: str = object_name[index]
        doubled: bool = object_name[index : index + 2] == QUOTED_IDENTIFIER_MARK * 2
        if quoted and doubled:
            current.append(QUOTED_IDENTIFIER_MARK)
            index += 2
            continue
        if character == QUOTED_IDENTIFIER_MARK:
            quoted = not quoted
            was_quoted = True
        elif character == NAME_SEPARATOR and not quoted:
            parts.append("".join(current) if was_quoted else "".join(current).upper())
            current, was_quoted = [], False
        else:
            current.append(character)
        index += 1
    parts.append("".join(current) if was_quoted else "".join(current).upper())
    return ".".join(parts)


def dependency_queries(*, databases: Iterable[str]) -> tuple[UsageQuery, ...]:
    """One OBJECT_DEPENDENCIES read of the view links in the given databases."""

    names: tuple[str, ...] = tuple(sorted(set(databases)))
    return tuple(
        dependency_query(databases=names[start : start + USAGE_NAME_CHUNK_SIZE])
        for start in range(0, len(names), USAGE_NAME_CHUNK_SIZE)
    )


def dependency_query(*, databases: tuple[str, ...]) -> UsageQuery:
    """What each view in the databases references, as `(referencing, referenced)` names."""

    placeholders: str = ", ".join(["%s"] * len(databases))
    domains: str = ", ".join(["%s"] * len(DEPENDENCY_VIEW_DOMAINS))
    sql: str = (
        "SELECT referencing_database || '.' || referencing_schema || '.' "
        "|| referencing_object_name AS referencing_name, "
        "referenced_database || '.' || referenced_schema || '.' || referenced_object_name "
        "AS referenced_name "
        "FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES "
        f"WHERE referencing_object_domain IN ({domains}) "
        f"AND referencing_database IN ({placeholders}) "
        "ORDER BY 1, 2"
    )
    return UsageQuery(sql=sql, params=(*DEPENDENCY_VIEW_DOMAINS, *databases))


def _folded(relation: RelationInfo | RelationUsage) -> tuple[str, str, str]:
    return (
        (relation.database or "").lower(),
        (relation.schema or "").lower(),
        relation.name.lower(),
    )


def walk_seeds(
    *, usages: Iterable[RelationUsage], relations_by_dependency_name: Mapping[str, RelationInfo]
) -> dict[str, tuple[str, RelationUsage]]:
    """Each directly read object to walk from, with its printed name and the usage it passes on."""

    names_by_key: dict[tuple[str, str, str], str] = {
        _folded(relation): name for name, relation in relations_by_dependency_name.items()
    }
    seeds: dict[str, tuple[str, RelationUsage]] = {}
    usage: RelationUsage
    for usage in usages:
        own: str | None = names_by_key.get(_folded(usage))
        if own is not None:
            seeds.setdefault(own, (display_name(own), usage))
        via: str
        for via in usage.via:
            seeds.setdefault(dependency_key(via), (via, usage))
    return seeds


def _via_seed(
    *, relation: RelationInfo, label: str, seed_usage: RelationUsage, earlier: RelationUsage | None
) -> RelationUsage:
    via: tuple[str, ...] = (label,)
    readers: tuple[str, ...] = seed_usage.readers
    last_read_at: datetime = seed_usage.last_read_at
    query_count: int = seed_usage.query_count
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


def _reachable(*, start: str, references: Mapping[str, set[str]]) -> list[str]:
    seen: set[str] = {start}
    pending: list[str] = [start]
    reached: list[str] = []
    while pending:
        node: str = pending.pop()
        child: str
        for child in sorted(references.get(node, set()) - seen):
            seen.add(child)
            reached.append(child)
            pending.append(child)
    return reached


def chained_usages(
    *,
    usages: tuple[RelationUsage, ...],
    dependencies: Iterable[tuple[str, str]],
    relations_by_dependency_name: Mapping[str, RelationInfo],
) -> tuple[RelationUsage, ...]:
    """Usages plus every unread candidate a directly read object depends on, through any views."""

    references: dict[str, set[str]] = {}
    referencing: str
    referenced: str
    for referencing, referenced in dependencies:
        references.setdefault(referencing, set()).add(referenced)
    seeds: dict[str, tuple[str, RelationUsage]] = walk_seeds(
        usages=usages, relations_by_dependency_name=relations_by_dependency_name
    )
    read_keys: frozenset[tuple[str, str, str]] = frozenset(map(_folded, usages))
    read: set[str] = {
        name
        for name, relation in relations_by_dependency_name.items()
        if _folded(relation) in read_keys
    }
    found: dict[str, RelationUsage] = {}
    seed: str
    for seed in sorted(seeds):
        label: str
        seed_usage: RelationUsage
        label, seed_usage = seeds[seed]
        child: str
        for child in _reachable(start=seed, references=references):
            if child in read or child not in relations_by_dependency_name:
                continue
            found[child] = _via_seed(
                relation=relations_by_dependency_name[child],
                label=label,
                seed_usage=seed_usage,
                earlier=found.get(child),
            )
    return (*usages, *(found[name] for name in sorted(found)))
