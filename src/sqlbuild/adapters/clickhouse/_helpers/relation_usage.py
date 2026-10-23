"""Read who queried relations from the ClickHouse system.query_log table."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from sqlbuild.adapter.contract.main.aggregate_relation_usage import aggregate_relation_usage
from sqlbuild.adapter.contract.models import RelationInfo, RelationRead, RelationUsageReport
from sqlbuild.adapters.clickhouse._helpers.type_text import quote_string
from sqlbuild.adapters.clickhouse.constants import (
    LOGGING_OFF_VALUES,
    LOGGING_SETTING_SQL,
    OTHER_REPLICAS_NOTICE,
    REPLICA_COUNT_SQL,
    USAGE_ERROR_CODE_PATTERN,
    USAGE_LOGGING_OFF_REASON,
    USAGE_NAME_CHUNK_SIZE,
    USAGE_QUERY_KINDS,
    USAGE_UNAVAILABLE_ERROR_CODES,
    USAGE_UNAVAILABLE_REASON,
)


def usage_object_names(*, relations: Iterable[RelationInfo]) -> dict[str, RelationInfo]:
    """Each relation by the `database.table` name query_log records; names keep their case."""

    return {
        f"{relation.schema}.{relation.name}": relation
        for relation in relations
        if relation.schema is not None
    }


def usage_queries(*, object_names: Iterable[str], window_seconds: int) -> tuple[str, ...]:
    """One query_log read per chunk of object names."""

    names: tuple[str, ...] = tuple(sorted(object_names))
    return tuple(
        usage_query(
            object_names=names[start : start + USAGE_NAME_CHUNK_SIZE],
            window_seconds=window_seconds,
        )
        for start in range(0, len(names), USAGE_NAME_CHUNK_SIZE)
    )


def usage_query(*, object_names: tuple[str, ...], window_seconds: int) -> str:
    """Finished reads and inserts of the named tables per initial user within the window."""

    since: str = f"now() - toIntervalSecond({int(window_seconds)})"
    kinds: str = ", ".join(quote_string(kind) for kind in USAGE_QUERY_KINDS)
    names: str = ", ".join(quote_string(name) for name in object_names)
    return (
        "SELECT object_name, initial_user AS user_name, "
        "uniqExact(initial_query_id) AS query_count, "
        "toUnixTimestamp(max(event_time)) AS last_read_at "
        "FROM system.query_log ARRAY JOIN tables AS object_name "
        f"WHERE event_date >= toDate({since}) "
        f"AND event_time >= {since} "
        "AND type = 'QueryFinish' "
        f"AND query_kind IN ({kinds}) "
        f"AND object_name IN ({names}) "
        "GROUP BY object_name, user_name "
        "ORDER BY object_name, user_name"
    )


def is_usage_unavailable_error(error: Exception) -> bool:
    """Whether reading query_log failed because it does not exist or may not be read."""

    match: re.Match[str] | None = USAGE_ERROR_CODE_PATTERN.search(str(error))
    return match is not None and int(match.group(1)) in USAGE_UNAVAILABLE_ERROR_CODES


def usage_reads(rows: Iterable[tuple[object, ...]]) -> tuple[RelationRead, ...]:
    """Reads from `(object, user, queries, last read as Unix seconds)` rows."""

    return tuple(
        RelationRead(
            object_name=str(row[0]),
            reader=str(row[1]) if row[1] else None,
            query_count=int(str(row[2])),
            last_read_at=datetime.fromtimestamp(int(str(row[3])), tz=UTC),
        )
        for row in rows
    )


def read_relation_usage(
    *,
    run_query: Callable[[str], list[tuple[object, ...]]],
    relations: tuple[RelationInfo, ...],
    window_seconds: int,
) -> RelationUsageReport:
    """Read every relation's usage; no query log or logging turned off means not checked."""

    relations_by_name: dict[str, RelationInfo] = usage_object_names(relations=relations)
    rows: list[tuple[object, ...]] = []
    try:
        logging: str = str(run_query(LOGGING_SETTING_SQL)[0][0]) if relations_by_name else ""
        if logging in LOGGING_OFF_VALUES:
            return RelationUsageReport(checked=False, reason=USAGE_LOGGING_OFF_REASON)
        sql: str
        for sql in usage_queries(object_names=relations_by_name, window_seconds=window_seconds):
            rows.extend(run_query(sql))
    except Exception as error:
        if not is_usage_unavailable_error(error):
            raise
        return RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON)
    return RelationUsageReport(
        checked=True,
        usages=aggregate_relation_usage(
            reads=usage_reads(rows), relations_by_name=relations_by_name
        ),
        notices=replica_notices(run_query=run_query) if relations_by_name else (),
    )


def replica_notices(*, run_query: Callable[[str], list[tuple[object, ...]]]) -> tuple[str, ...]:
    """A notice when this server's shard has other replicas, whose query logs are not read."""

    try:
        rows: list[tuple[object, ...]] = run_query(REPLICA_COUNT_SQL)
    except Exception as error:
        if not is_usage_unavailable_error(error):
            raise
        return ()
    replicas: int = int(str(rows[0][0] or 0)) if rows else 0
    return (OTHER_REPLICAS_NOTICE,) if replicas > 1 else ()
