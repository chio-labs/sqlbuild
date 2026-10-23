"""Read who queried relations from the Databricks system.access.table_lineage table."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlbuild.adapter.contract.main.aggregate_relation_usage import aggregate_relation_usage
from sqlbuild.adapter.contract.main.relation_reads import relation_reads
from sqlbuild.adapter.contract.models import RelationInfo, RelationUsageReport
from sqlbuild.adapters.databricks.constants import (
    LINEAGE_VIEW_SOURCE_TYPES,
    USAGE_NAME_CHUNK_SIZE,
    USAGE_UNAVAILABLE_ERROR_CLASSES,
    USAGE_UNAVAILABLE_REASON,
    USAGE_UNAVAILABLE_SQLSTATES,
)
from sqlbuild.adapters.databricks.models import UsageQuery


def usage_object_names(*, relations: Iterable[RelationInfo]) -> dict[str, RelationInfo]:
    """Each fully qualified relation by its lowercase `catalog.schema.table` lineage name."""

    named: dict[str, RelationInfo] = {}
    relation: RelationInfo
    for relation in relations:
        if relation.database is None or relation.schema is None:
            continue
        name: str = ".".join(
            part.replace("`", "").lower()
            for part in (relation.database, relation.schema, relation.name)
        )
        named[name] = relation
    return named


def usage_queries(*, object_names: Iterable[str], window_seconds: int) -> tuple[UsageQuery, ...]:
    """One lineage read per chunk of object names."""

    names: tuple[str, ...] = tuple(sorted(object_names))
    return tuple(
        usage_query(
            object_names=names[start : start + USAGE_NAME_CHUNK_SIZE],
            window_seconds=window_seconds,
        )
        for start in range(0, len(names), USAGE_NAME_CHUNK_SIZE)
    )


def usage_query(*, object_names: tuple[str, ...], window_seconds: int) -> UsageQuery:
    """Read events of the named tables per user within the window, direct or through views."""

    placeholders: str = ", ".join(f":name_{index}" for index in range(len(object_names)))
    since: str = "TIMESTAMPADD(SECOND, -:window_seconds, current_timestamp())"
    view_types: str = ", ".join(f"'{source_type}'" for source_type in LINEAGE_VIEW_SOURCE_TYPES)
    sql: str = (
        "WITH lineage AS ("
        "SELECT lower(source_table_full_name) AS object_name, source_type, created_by, "
        "event_time, statement_id, event_id, COALESCE(direct_access, true) AS direct "
        "FROM system.access.table_lineage "
        f"WHERE event_date >= DATE({since}) "
        f"AND event_time >= {since} "
        "AND source_table_full_name IS NOT NULL), "
        f"reads AS (SELECT * FROM lineage WHERE object_name IN ({placeholders})), "
        "via AS ("
        "SELECT reads.object_name, reads.created_by, collect_set(views.object_name) AS via_names "
        "FROM reads JOIN lineage AS views ON views.statement_id = reads.statement_id "
        f"AND views.direct AND views.source_type IN ({view_types}) "
        "WHERE NOT reads.direct GROUP BY 1, 2) "
        "SELECT reads.object_name, reads.created_by AS user_name, "
        "COUNT(DISTINCT COALESCE(reads.statement_id, reads.event_id)) AS query_count, "
        "MAX(reads.event_time) AS last_read_at, "
        "bool_or(reads.direct) AS direct, "
        "first(via.via_names) AS via_names "
        "FROM reads LEFT JOIN via ON via.object_name = reads.object_name "
        "AND via.created_by <=> reads.created_by "
        "GROUP BY 1, 2 "
        "ORDER BY 1, 2"
    )
    params: dict[str, object] = {"window_seconds": window_seconds}
    params.update({f"name_{index}": name for index, name in enumerate(object_names)})
    return UsageQuery(sql=sql, params=params)


def is_usage_unavailable_error(error: Exception) -> bool:
    """Whether reading lineage failed for Unity Catalog, system schema or permission reasons."""

    message: str = str(error).upper()
    return getattr(error, "sqlstate", None) in USAGE_UNAVAILABLE_SQLSTATES or any(
        error_class in message for error_class in USAGE_UNAVAILABLE_ERROR_CLASSES
    )


def read_relation_usage(
    *, connection: Any, relations: tuple[RelationInfo, ...], window_seconds: int
) -> RelationUsageReport:
    """Read every relation's usage in chunked queries; no lineage access means not checked."""

    relations_by_name: dict[str, RelationInfo] = usage_object_names(relations=relations)
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
        usages=aggregate_relation_usage(
            reads=relation_reads(rows=rows), relations_by_name=relations_by_name
        ),
    )
