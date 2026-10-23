"""BigQuery relation usage reads each location's INFORMATION_SCHEMA.JOBS per chunk of tables."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsageReport
from sqlbuild.adapters.bigquery.constants import CLONE_STATEMENT_PATTERN, USAGE_UNAVAILABLE_REASON
from tests.unit.src.sqlbuild.adapters.bigquery._test_types import (
    BigQueryCloneStatementTestCase,
    BigQueryRelationUsageChunkTestCase,
    BigQueryRelationUsageErrorTestCase,
    BigQueryRelationUsageFailureTestCase,
    BigQueryRelationUsageQueryTestCase,
    BigQueryRelationUsageTestCase,
)
from tests.unit.src.sqlbuild.adapters.bigquery.helpers import (
    FakeBigQueryError,
    FakeUsageClient,
    Forbidden,
    queried_names,
    read_bigquery_usage,
    usage_relation,
)

WINDOW_SECONDS: int = 7 * 86_400
READ_AT: datetime = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
EARLIER_READ_AT: datetime = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
ORDERS_DAILY: tuple[RelationInfo, ...] = (usage_relation(None, "mart", "orders_daily"),)
LOCATIONS: dict[str, str] = {"shop-analytics.mart": "EU", "shop-archive.mart": "us-east1"}


@pytest.mark.parametrize(
    "test_case",
    (
        BigQueryRelationUsageTestCase(
            description="reads per user add up, readers rank by jobs, the latest read wins",
            relations=((None, "mart", "orders_daily"), (None, "mart", "customers")),
            dataset_locations=LOCATIONS,
            rows=(
                ("shop-analytics.mart.orders_daily", "svc-reporting@example.com", 10, READ_AT),
                ("shop-analytics.mart.orders_daily", "alice@example.com", 4, EARLIER_READ_AT),
                ("shop-analytics.mart.orders_daily", None, 1, EARLIER_READ_AT),
                ("shop-analytics.mart.products", "bob@example.com", 3, READ_AT),
            ),
            expected_queries=(
                (
                    "`shop-analytics.region-eu`.INFORMATION_SCHEMA.JOBS",
                    "EU",
                    ("shop-analytics.mart.customers", "shop-analytics.mart.orders_daily"),
                ),
            ),
            expected_usages=(
                (
                    "orders_daily",
                    ("svc-reporting@example.com", "alice@example.com", "unknown user"),
                    15,
                    READ_AT,
                ),
            ),
        ),
        BigQueryRelationUsageTestCase(
            description="each project and dataset location gets its own read; case is kept",
            relations=(("shop-archive", "mart", "Orders_2025"), (None, "mart", "orders_daily")),
            dataset_locations=LOCATIONS,
            rows=(("shop-archive.mart.Orders_2025", "alice@example.com", 2, READ_AT),),
            expected_queries=(
                (
                    "`shop-analytics.region-eu`.INFORMATION_SCHEMA.JOBS",
                    "EU",
                    ("shop-analytics.mart.orders_daily",),
                ),
                (
                    "`shop-archive.region-us-east1`.INFORMATION_SCHEMA.JOBS",
                    "us-east1",
                    ("shop-archive.mart.Orders_2025",),
                ),
            ),
            expected_usages=(("Orders_2025", ("alice@example.com",), 2, READ_AT),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_jobs_history_when_reading_usage_then_reads_match_candidates(
    test_case: BigQueryRelationUsageTestCase,
) -> None:
    client: FakeUsageClient = FakeUsageClient(
        project="shop-analytics", dataset_locations=test_case.dataset_locations, rows=test_case.rows
    )

    report: RelationUsageReport = read_bigquery_usage(
        client=client,
        relations=tuple(usage_relation(*relation) for relation in test_case.relations),
        window_seconds=WINDOW_SECONDS,
    )

    assert report.checked
    assert tuple(
        (sql.split(" FROM ")[1].split(" WHERE ")[0], location, queried_names(params))
        for sql, location, params in client.queries
    ) == (test_case.expected_queries)
    assert tuple(
        (usage.name, usage.readers, usage.query_count, usage.last_read_at)
        for usage in report.usages
    ) == (test_case.expected_usages)


@pytest.mark.parametrize(
    "test_case",
    (
        BigQueryRelationUsageQueryTestCase(
            description="successful query jobs count; scripts, snapshots and clones do not",
            window_seconds=WINDOW_SECONDS,
            expected_params={
                "window_seconds": WINDOW_SECONDS,
                "clone_pattern": CLONE_STATEMENT_PATTERN,
                "object_names": ["shop-analytics.mart.orders_daily"],
            },
            expected_sql_fragments=(
                "UNNEST(jobs.referenced_tables) AS referenced",
                "UNNEST(jobs.referenced_logical_views) AS referenced",
                "INTERVAL @window_seconds SECOND",
                "job_type = 'QUERY'",
                "error_result IS NULL",
                "NOT IN ('SCRIPT', 'CREATE_SNAPSHOT_TABLE')",
                "AND NOT (STARTS_WITH(COALESCE(statement_type, ''), 'CREATE_TABLE') "
                "AND REGEXP_CONTAINS(query, @clone_pattern))",
                "WHERE object_name IN UNNEST(@object_names)",
                "COUNT(DISTINCT job_id) AS query_count",
                "user_email AS user_name",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_jobs_query_when_built_then_parameters_are_bound_and_clones_excluded(
    test_case: BigQueryRelationUsageQueryTestCase,
) -> None:
    client: FakeUsageClient = FakeUsageClient(project="shop-analytics", dataset_locations=LOCATIONS)

    read_bigquery_usage(
        client=client, relations=ORDERS_DAILY, window_seconds=test_case.window_seconds
    )

    sql: str
    params: dict[str, object]
    ((sql, _, params),) = client.queries
    assert params == test_case.expected_params
    assert all(fragment in sql for fragment in test_case.expected_sql_fragments)


@pytest.mark.parametrize(
    "test_case",
    (
        BigQueryRelationUsageChunkTestCase(
            description="no candidates read nothing",
            relation_count=0,
            expected_query_names=(),
        ),
        BigQueryRelationUsageChunkTestCase(
            description="a large candidate set is split into arrays of at most 1,000 names",
            relation_count=2_001,
            expected_query_names=(1_000, 1_000, 1),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_many_candidates_when_reading_usage_then_names_are_chunked(
    test_case: BigQueryRelationUsageChunkTestCase,
) -> None:
    client: FakeUsageClient = FakeUsageClient(project="shop-analytics", dataset_locations=LOCATIONS)

    report: RelationUsageReport = read_bigquery_usage(
        client=client,
        relations=tuple(
            usage_relation(None, "mart", f"old_orders_{index:04d}")
            for index in range(test_case.relation_count)
        ),
        window_seconds=WINDOW_SECONDS,
    )

    assert report.checked
    assert tuple(len(queried_names(params)) for _, _, params in client.queries) == (
        test_case.expected_query_names
    )


@pytest.mark.parametrize(
    "test_case",
    (
        BigQueryRelationUsageErrorTestCase(
            description="a missing jobs.listAll permission is not checked",
            error=FakeBigQueryError(
                "Access Denied: Table shop-analytics:region-eu.INFORMATION_SCHEMA.JOBS: User "
                "does not have permission bigquery.jobs.listAll",
                403,
            ),
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
        BigQueryRelationUsageErrorTestCase(
            description="an unknown region is not checked",
            error=FakeBigQueryError("Not found: Dataset shop-analytics:region-xx", 404),
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
        BigQueryRelationUsageErrorTestCase(
            description="a Forbidden error is not checked",
            error=Forbidden("403 GET jobs"),
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_no_jobs_access_when_reading_usage_then_usage_is_not_checked(
    test_case: BigQueryRelationUsageErrorTestCase,
) -> None:
    client: FakeUsageClient = FakeUsageClient(
        project="shop-analytics", dataset_locations=LOCATIONS, errors=(test_case.error,)
    )

    report: RelationUsageReport = read_bigquery_usage(
        client=client, relations=ORDERS_DAILY, window_seconds=WINDOW_SECONDS
    )

    assert report == test_case.expected_report


@pytest.mark.parametrize(
    "test_case",
    (
        BigQueryRelationUsageFailureTestCase(
            description="a quota failure is a real error",
            error=FakeBigQueryError("Quota exceeded: too many concurrent queries", 400),
            expected_error_match="Quota exceeded",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_other_jobs_failure_when_reading_usage_then_error_propagates(
    test_case: BigQueryRelationUsageFailureTestCase,
) -> None:
    client: FakeUsageClient = FakeUsageClient(
        project="shop-analytics", dataset_locations=LOCATIONS, errors=(test_case.error,)
    )

    with pytest.raises(FakeBigQueryError, match=test_case.expected_error_match):
        read_bigquery_usage(client=client, relations=ORDERS_DAILY, window_seconds=WINDOW_SECONDS)


@pytest.mark.parametrize(
    "test_case",
    (
        BigQueryCloneStatementTestCase(
            description="a table clone",
            statement="CREATE TABLE mart.orders_copy CLONE mart.orders",
            expected_clone=True,
        ),
        BigQueryCloneStatementTestCase(
            description="a replaced clone of a quoted name at a point in time",
            statement="create or replace table `shop-analytics.mart.orders_copy` clone "
            "`shop-analytics.mart.orders` FOR SYSTEM_TIME AS OF TIMESTAMP '2026-10-01'",
            expected_clone=True,
        ),
        BigQueryCloneStatementTestCase(
            description="a clone after a leading comment",
            statement="# nightly copy\nCREATE TABLE IF NOT EXISTS mart.orders_copy CLONE mart.orders;",
            expected_clone=True,
        ),
        BigQueryCloneStatementTestCase(
            description="a CTAS selecting a column named clone",
            statement="CREATE TABLE mart.orders_copy AS SELECT clone FROM mart.orders",
            expected_clone=False,
        ),
        BigQueryCloneStatementTestCase(
            description="a CTAS with clone inside a string",
            statement="CREATE TABLE mart.notes AS SELECT 'orders CLONE copy' AS note",
            expected_clone=False,
        ),
        BigQueryCloneStatementTestCase(
            description="a CTAS whose comment mentions a clone",
            statement="CREATE TABLE mart.c AS SELECT 1 AS n -- not CREATE TABLE a CLONE b",
            expected_clone=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_statement_when_matching_clone_pattern_then_only_clones_match(
    test_case: BigQueryCloneStatementTestCase,
) -> None:
    matched: bool = re.search(CLONE_STATEMENT_PATTERN, test_case.statement) is not None

    assert matched == test_case.expected_clone


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
