"""Read who queried relations from Snowflake ACCOUNT_USAGE access history."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsage, RelationUsageReport
from sqlbuild.adapters.snowflake.constants import (
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
    """Reads of the named objects per user, excluding SQLBuild-tagged queries and clones."""

    placeholders: str = ", ".join(["%s"] * len(object_names))
    sql: str = (
        'SELECT accessed.value:"objectName"::STRING AS object_name, '
        "history.user_name AS user_name, "
        "COUNT(DISTINCT history.query_id) AS query_count, "
        "MAX(history.query_start_time) AS last_read_at "
        "FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY AS history, "
        "LATERAL FLATTEN(INPUT => history.direct_objects_accessed) AS accessed "
        "WHERE history.query_start_time >= DATEADD('second', -%s, CURRENT_TIMESTAMP()) "
        f'AND accessed.value:"objectName"::STRING IN ({placeholders}) '
        "AND NOT EXISTS ("
        "SELECT 1 FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY AS query "
        "WHERE query.query_id = history.query_id "
        "AND query.start_time >= DATEADD('second', -%s, CURRENT_TIMESTAMP()) "
        "AND (CONTAINS(COALESCE(query.query_tag, ''), %s) "
        "OR (STARTSWITH(query.query_type, 'CREATE') "
        "AND REGEXP_LIKE(query.query_text, %s, 'is')))"
        ") "
        "GROUP BY 1, 2 "
        "ORDER BY 1, 2"
    )
    return UsageQuery(
        sql=sql,
        params=(
            window_seconds,
            *object_names,
            window_seconds,
            SQLBUILD_QUERY_TAG_FRAGMENT,
            CLONE_STATEMENT_PATTERN,
        ),
    )


def relation_usages(
    *, rows: Iterable[tuple[object, ...]], relations_by_name: Mapping[str, RelationInfo]
) -> tuple[RelationUsage, ...]:
    """One usage per read relation from `(object_name, user, query_count, last_read)` rows."""

    readers: dict[str, dict[str, int]] = {}
    last_read: dict[str, datetime] = {}
    row: tuple[object, ...]
    for row in rows:
        object_name: str = str(row[0])
        if object_name not in relations_by_name:
            continue
        user: str = str(row[1])
        counts: dict[str, int] = readers.setdefault(object_name, {})
        counts[user] = counts.get(user, 0) + int(str(row[2]))
        read_at: datetime = _utc(row[3])
        last_read[object_name] = max(read_at, last_read.get(object_name, read_at))
    usages: list[RelationUsage] = []
    object_name: str
    for object_name in sorted(readers):
        relation: RelationInfo = relations_by_name[object_name]
        counts = readers[object_name]
        usages.append(
            RelationUsage(
                database=relation.database,
                schema=relation.schema,
                name=relation.name,
                last_read_at=last_read[object_name],
                readers=tuple(sorted(counts, key=lambda user: (-counts[user], user))),
                query_count=sum(counts.values()),
            )
        )
    return tuple(usages)


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
    """Read every relation's usage in chunked queries; no access history means not checked."""

    database: str | None = None
    if any(relation.database is None for relation in relations):
        database = current_database()
    relations_by_name: dict[str, RelationInfo] = usage_object_names(
        relations=relations, current_database=database
    )
    rows: list[tuple[object, ...]] = []
    query: UsageQuery
    for query in usage_queries(object_names=relations_by_name, window_seconds=window_seconds):
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query.sql, query.params)
            rows.extend(tuple(row) for row in cursor.fetchall())
        except Exception as error:
            if not is_usage_unavailable_error(error):
                raise
            return RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON)
        finally:
            cursor.close()
    return RelationUsageReport(
        checked=True,
        usages=relation_usages(rows=rows, relations_by_name=relations_by_name),
    )
