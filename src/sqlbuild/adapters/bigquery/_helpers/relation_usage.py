"""Read who queried relations from BigQuery INFORMATION_SCHEMA.JOBS."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlbuild.adapter.contract.main.aggregate_relation_usage import aggregate_relation_usage
from sqlbuild.adapter.contract.main.relation_reads import relation_reads
from sqlbuild.adapter.contract.models import RelationInfo, RelationUsageReport
from sqlbuild.adapters.bigquery.constants import (
    CLONE_STATEMENT_PATTERN,
    FORBIDDEN_ERROR_CLASS_NAMES,
    FORBIDDEN_STATUS,
    NOT_FOUND_ERROR_CLASS_NAMES,
    NOT_FOUND_STATUS,
    USAGE_NAME_CHUNK_SIZE,
    USAGE_UNAVAILABLE_ERROR_REASONS,
    USAGE_UNAVAILABLE_MESSAGES,
)
from sqlbuild.adapters.bigquery.models import UsageQuery

_USAGE_UNAVAILABLE_REASON: str = (
    "cannot read INFORMATION_SCHEMA.JOBS "
    "(needs bigquery.jobs.listAll, for example the BigQuery Resource Viewer role)"
)


def usage_object_name(*, project: str, dataset: str, table: str) -> str:
    """`project.dataset.table` as `referenced_tables` spells it; BigQuery names keep their case."""

    return ".".join(part.replace("`", "") for part in (project, dataset, table))


def usage_queries(
    *,
    relations: Iterable[RelationInfo],
    default_project: str,
    locations: Mapping[tuple[str, str], str],
    window_seconds: int,
) -> tuple[tuple[UsageQuery, dict[str, RelationInfo]], ...]:
    """One JOBS read per project, location and chunk of names, with the relations it covers."""

    groups: dict[tuple[str, str], dict[str, RelationInfo]] = {}
    relation: RelationInfo
    for relation in relations:
        if relation.schema is None:
            continue
        project: str = relation_project(relation=relation, default_project=default_project)
        location: str = locations[(project, relation.schema)]
        name: str = usage_object_name(project=project, dataset=relation.schema, table=relation.name)
        groups.setdefault((project, location), {})[name] = relation
    queries: list[tuple[UsageQuery, dict[str, RelationInfo]]] = []
    for (project, location), named in sorted(groups.items()):
        names: tuple[str, ...] = tuple(sorted(named))
        for start in range(0, len(names), USAGE_NAME_CHUNK_SIZE):
            chunk: tuple[str, ...] = names[start : start + USAGE_NAME_CHUNK_SIZE]
            queries.append(
                (
                    usage_query(
                        project=project,
                        location=location,
                        object_names=chunk,
                        window_seconds=window_seconds,
                    ),
                    {name: named[name] for name in chunk},
                )
            )
    return tuple(queries)


def jobs_view(*, project: str, location: str) -> str:
    """`project.region-<location>`.INFORMATION_SCHEMA.JOBS."""

    region: str = location.strip().lower()
    region = region if region.startswith("region-") else f"region-{region}"
    return f"`{project}.{region}`.INFORMATION_SCHEMA.JOBS"


def usage_query(
    *, project: str, location: str, object_names: tuple[str, ...], window_seconds: int
) -> UsageQuery:
    """Reads of the named tables and views per user by successful query jobs, minus clones."""

    def referenced(column: str) -> str:
        return (
            "SELECT CONCAT(referenced.project_id, '.', referenced.dataset_id, '.', "
            "referenced.table_id) AS object_name, "
            "jobs.user_email, jobs.job_id, jobs.creation_time "
            f"FROM jobs, UNNEST(jobs.{column}) AS referenced"
        )

    sql: str = (
        "WITH jobs AS ("
        "SELECT job_id, user_email, creation_time, referenced_tables, referenced_logical_views "
        f"FROM {jobs_view(project=project, location=location)} "
        "WHERE creation_time >= "
        "TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @window_seconds SECOND) "
        "AND job_type = 'QUERY' "
        "AND error_result IS NULL "
        "AND COALESCE(statement_type, '') NOT IN ('SCRIPT', 'CREATE_SNAPSHOT_TABLE') "
        "AND NOT (STARTS_WITH(COALESCE(statement_type, ''), 'CREATE_TABLE') "
        "AND REGEXP_CONTAINS(query, @clone_pattern))), "
        f"reads AS ({referenced('referenced_tables')} UNION ALL "
        f"{referenced('referenced_logical_views')}) "
        "SELECT object_name, user_email AS user_name, "
        "COUNT(DISTINCT job_id) AS query_count, "
        "MAX(creation_time) AS last_read_at "
        "FROM reads "
        "WHERE object_name IN UNNEST(@object_names) "
        "GROUP BY 1, 2 "
        "ORDER BY 1, 2"
    )
    return UsageQuery(
        sql=sql, location=location, window_seconds=window_seconds, object_names=object_names
    )


def query_parameters(query: UsageQuery) -> list[Any]:
    """The query's parameters as BigQuery client parameters."""

    from google.cloud import bigquery

    return [
        bigquery.ScalarQueryParameter("window_seconds", "INT64", query.window_seconds),
        bigquery.ScalarQueryParameter("clone_pattern", "STRING", CLONE_STATEMENT_PATTERN),
        bigquery.ArrayQueryParameter("object_names", "STRING", list(query.object_names)),
    ]


def is_usage_unavailable_error(error: Exception) -> bool:
    """Whether reading JOBS failed because the view or the permission to list jobs is missing."""

    reasons: frozenset[str] = error_reasons(error)
    if reasons:
        return reasons <= USAGE_UNAVAILABLE_ERROR_REASONS
    code: object = getattr(error, "code", None)
    name: str = type(error).__name__
    if code == NOT_FOUND_STATUS or name in NOT_FOUND_ERROR_CLASS_NAMES:
        return True
    message: str = str(error).lower()
    return (code == FORBIDDEN_STATUS or name in FORBIDDEN_ERROR_CLASS_NAMES) and any(
        marker in message for marker in USAGE_UNAVAILABLE_MESSAGES
    )


def error_reasons(error: Exception) -> frozenset[str]:
    """The `reason` of each error detail Google reports, such as `accessDenied`."""

    details: object = getattr(error, "errors", None)
    reasons: set[str] = set()
    if isinstance(details, list):
        reasons.update(
            str(detail["reason"])
            for detail in details
            if isinstance(detail, dict) and detail.get("reason")
        )
    reason: object = getattr(error, "reason", None)
    if isinstance(reason, str) and reason:
        reasons.add(reason)
    return frozenset(reasons)


def relation_project(*, relation: RelationInfo, default_project: str) -> str:
    """The project holding the relation: its database, else the client's project."""

    return (relation.database or default_project).replace("`", "")


def dataset_locations(
    *, connection: Any, relations: Iterable[RelationInfo], default_project: str
) -> dict[tuple[str, str], str]:
    """The location of each candidate's dataset, or the connection's fixed location."""

    keys: set[tuple[str, str]] = {
        (relation_project(relation=relation, default_project=default_project), relation.schema)
        for relation in relations
        if relation.schema is not None
    }
    if connection.location is not None:
        return {key: str(connection.location) for key in keys}
    return {
        key: str(connection.client.get_dataset(f"{key[0]}.{key[1]}").location)
        for key in sorted(keys)
    }


def run_usage_query(*, connection: Any, query: UsageQuery) -> list[tuple[object, ...]]:
    """Run one JOBS read with bound parameters in the query's location."""

    return list(
        connection.run_statement(
            sql=query.sql,
            location=query.location,
            query_parameters=tuple(query_parameters(query)),
        ).fetchall()
    )


def read_relation_usage(
    *, connection: Any, relations: tuple[RelationInfo, ...], window_seconds: int
) -> RelationUsageReport:
    """Read every relation's usage in each dataset's location."""

    default_project: str = str(connection.client.project)
    rows: list[tuple[object, ...]] = []
    covered: dict[str, RelationInfo] = {}
    query: UsageQuery
    named: dict[str, RelationInfo]
    for query, named in usage_queries(
        relations=relations,
        default_project=default_project,
        locations=dataset_locations(
            connection=connection, relations=relations, default_project=default_project
        ),
        window_seconds=window_seconds,
    ):
        rows.extend(run_usage_query(connection=connection, query=query))
        covered.update(named)
    return RelationUsageReport(
        checked=True,
        usages=aggregate_relation_usage(
            reads=relation_reads(rows=rows),
            relations_by_name=covered,
        ),
    )


def bigquery_relation_usage(
    *, connection: Any, relations: tuple[RelationInfo, ...], window_seconds: int
) -> RelationUsageReport:
    """Read usage; no access to JOBS or the datasets means usage is not checked."""

    try:
        return read_relation_usage(
            connection=connection, relations=relations, window_seconds=window_seconds
        )
    except Exception as error:
        if not is_usage_unavailable_error(error):
            raise
        return RelationUsageReport(checked=False, reason=_USAGE_UNAVAILABLE_REASON)
