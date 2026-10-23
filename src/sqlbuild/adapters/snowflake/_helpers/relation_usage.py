"""Read who queried relations from Snowflake ACCOUNT_USAGE access history."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from sqlbuild.adapter.contract.main.aggregate_relation_usage import aggregate_relation_usage
from sqlbuild.adapter.contract.main.relation_reads import relation_reads
from sqlbuild.adapter.contract.models import RelationInfo, RelationUsage, RelationUsageReport
from sqlbuild.adapters.snowflake._helpers.view_dependencies import (
    chained_usages,
    dependency_name,
    dependency_queries,
    display_name,
    walk_seeds,
)
from sqlbuild.adapters.snowflake.constants import (
    CHAINS_NOT_FOLLOWED_NOTICE,
    CLONE_STATEMENT_PATTERN,
    SQLBUILD_QUERY_TAG_FRAGMENT,
    USAGE_NAME_CHUNK_SIZE,
    USAGE_UNAVAILABLE_REASON,
)
from sqlbuild.adapters.snowflake.models import UsageQuery

_UNQUOTED_IDENTIFIER: re.Pattern[str] = re.compile(r"^[A-Z_][A-Z0-9_$]*$")
_UNAVAILABLE_ERRNOS: frozenset[int] = frozenset({2003, 3001})
_UNAVAILABLE_MESSAGES: tuple[str, ...] = (
    "does not exist or not authorized",
    "insufficient privileges",
)


def usage_object_name(*, database: str, schema: str, name: str) -> str:
    """The `objectName` access history records for a relation SQLBuild names unquoted."""

    return ".".join(_object_name_part(part) for part in (database, schema, name))


def _object_name_part(part: str) -> str:
    folded: str = part.upper()
    if _UNQUOTED_IDENTIFIER.match(folded):
        return folded
    return '"' + folded.replace('"', '""') + '"'


def usage_object_names(
    *, relations: Iterable[RelationInfo], current_database: str | None
) -> dict[str, RelationInfo]:
    """Each schema-qualified relation by its access-history object name."""

    named: dict[str, RelationInfo] = {}
    relation: RelationInfo
    for relation in relations:
        database: str | None = relation.database or current_database
        if database is None or relation.schema is None:
            continue
        named[usage_object_name(database=database, schema=relation.schema, name=relation.name)] = (
            relation
        )
    return named


def usage_queries(*, object_names: Iterable[str], window_seconds: int) -> tuple[UsageQuery, ...]:
    """One access-history read per chunk of object names, oldest read within the window."""

    names: tuple[str, ...] = tuple(sorted(object_names))
    return tuple(
        usage_query(
            object_names=names[start : start + USAGE_NAME_CHUNK_SIZE],
            window_seconds=window_seconds,
        )
        for start in range(0, len(names), USAGE_NAME_CHUNK_SIZE)
    )


def usage_query(*, object_names: tuple[str, ...], window_seconds: int) -> UsageQuery:
    """Reads of the named objects per user, direct or through views, minus SQLBuild and clones."""

    placeholders: str = ", ".join(["%s"] * len(object_names))
    since: str = "DATEADD('second', -%s, CURRENT_TIMESTAMP())"
    object_name: str = 'accessed.value:"objectName"::STRING'
    sql: str = (
        "WITH history AS ("
        "SELECT query_id, user_name, query_start_time, direct_objects_accessed, "
        "base_objects_accessed FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY "
        f"WHERE query_start_time >= {since}), "
        "direct_reads AS ("
        "SELECT history.query_id, history.user_name, history.query_start_time, "
        f"{object_name} AS object_name "
        "FROM history, LATERAL FLATTEN(INPUT => history.direct_objects_accessed) AS accessed "
        f"WHERE {object_name} IN ({placeholders})), "
        "base_reads AS ("
        "SELECT history.query_id, history.user_name, history.query_start_time, "
        f"{object_name} AS object_name "
        "FROM history, LATERAL FLATTEN(INPUT => history.base_objects_accessed) AS accessed "
        f"WHERE {object_name} IN ({placeholders})), "
        "candidate_reads AS ("
        "SELECT query_id, user_name, query_start_time, object_name, TRUE AS direct "
        "FROM direct_reads UNION ALL "
        "SELECT base.query_id, base.user_name, base.query_start_time, base.object_name, FALSE "
        "FROM base_reads AS base WHERE NOT EXISTS ("
        "SELECT 1 FROM direct_reads AS direct_read "
        "WHERE direct_read.query_id = base.query_id "
        "AND direct_read.object_name = base.object_name)), "
        "reads AS ("
        "SELECT * FROM candidate_reads AS candidate WHERE NOT EXISTS ("
        "SELECT 1 FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY AS query "
        "WHERE query.query_id = candidate.query_id "
        f"AND query.start_time >= {since} "
        "AND (CONTAINS(COALESCE(query.query_tag, ''), %s) "
        "OR (STARTSWITH(query.query_type, 'CREATE') "
        "AND REGEXP_LIKE(query.query_text, %s, 'is'))))), "
        "via AS ("
        f"SELECT reads.object_name, reads.user_name, ARRAY_AGG(DISTINCT {object_name}) "
        "AS via_names "
        "FROM reads JOIN history ON history.query_id = reads.query_id, "
        "LATERAL FLATTEN(INPUT => history.direct_objects_accessed) AS accessed "
        "WHERE NOT reads.direct GROUP BY 1, 2) "
        "SELECT reads.object_name, reads.user_name, "
        "COUNT(DISTINCT reads.query_id) AS query_count, "
        "MAX(reads.query_start_time) AS last_read_at, "
        "BOOLOR_AGG(reads.direct) AS direct, "
        "ANY_VALUE(via.via_names) AS via_names "
        "FROM reads LEFT JOIN via "
        "ON via.object_name = reads.object_name AND via.user_name = reads.user_name "
        "GROUP BY 1, 2 "
        "ORDER BY 1, 2"
    )
    return UsageQuery(
        sql=sql,
        params=(
            window_seconds,
            *object_names,
            *object_names,
            window_seconds,
            SQLBUILD_QUERY_TAG_FRAGMENT,
            CLONE_STATEMENT_PATTERN,
        ),
    )


def is_usage_unavailable_error(error: Exception) -> bool:
    """Whether reading access history failed for edition or privilege reasons."""

    message: str = str(error).lower()
    return getattr(error, "errno", None) in _UNAVAILABLE_ERRNOS or any(
        marker in message for marker in _UNAVAILABLE_MESSAGES
    )


def read_relation_usage(
    *,
    connection: Any,
    relations: tuple[RelationInfo, ...],
    window_seconds: int,
    current_database: Callable[[], str | None],
) -> RelationUsageReport:
    """Read every relation's usage and view dependencies; no access history means not checked."""

    database: str | None = None
    if any(relation.database is None for relation in relations):
        database = current_database()
    relations_by_name: dict[str, RelationInfo] = usage_object_names(
        relations=relations, current_database=database
    )
    by_dependency_name: dict[str, RelationInfo] = {}
    relation: RelationInfo
    for relation in relations:
        name: str | None = dependency_name(relation=relation, current_database=database)
        if name is not None:
            by_dependency_name[name] = relation
    try:
        rows: list[tuple[object, ...]] = _fetch(
            connection=connection,
            queries=usage_queries(object_names=relations_by_name, window_seconds=window_seconds),
        )
    except Exception as error:
        if not is_usage_unavailable_error(error):
            raise
        return RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON)
    usages: tuple[RelationUsage, ...] = aggregate_relation_usage(
        reads=relation_reads(rows=rows, via_name=display_name),
        relations_by_name=relations_by_name,
    )
    seeds: dict[str, tuple[str, RelationUsage]] = walk_seeds(
        usages=usages, relations_by_dependency_name=by_dependency_name
    )
    try:
        dependencies: list[tuple[object, ...]] = _fetch(
            connection=connection,
            queries=dependency_queries(
                databases=dependency_databases(seeds=seeds, candidates=by_dependency_name)
            ),
        )
    except Exception as error:
        if not is_usage_unavailable_error(error):
            raise
        return RelationUsageReport(
            checked=True, usages=usages, notices=(CHAINS_NOT_FOLLOWED_NOTICE,)
        )
    return RelationUsageReport(
        checked=True,
        usages=chained_usages(
            usages=usages,
            dependencies=((str(row[0]), str(row[1])) for row in dependencies),
            relations_by_dependency_name=by_dependency_name,
        ),
    )


def dependency_databases(*, seeds: Iterable[str], candidates: Iterable[str]) -> frozenset[str]:
    """The databases of the walk's start objects and the candidates; none without a start."""

    starts: tuple[str, ...] = tuple(seeds)
    if not starts:
        return frozenset()
    return frozenset(name.split(".", 1)[0] for name in (*starts, *candidates))


def _fetch(*, connection: Any, queries: tuple[UsageQuery, ...]) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    query: UsageQuery
    for query in queries:
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query.sql, query.params)
            rows.extend(tuple(row) for row in cursor.fetchall())
        finally:
            cursor.close()
    return rows
