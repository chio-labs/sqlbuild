"""ClickHouse relation usage reads this node's system.query_log once per chunk of candidates."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsageReport
from sqlbuild.adapters.clickhouse.constants import (
    USAGE_LOGGING_OFF_REASON,
    USAGE_UNAVAILABLE_REASON,
)
from tests.unit.src.sqlbuild.adapters.clickhouse._test_types import (
    ClickHouseRelationUsageChunkTestCase,
    ClickHouseRelationUsageFailureTestCase,
    ClickHouseRelationUsageQueryTestCase,
    ClickHouseRelationUsageReplicaTestCase,
    ClickHouseRelationUsageTestCase,
    ClickHouseRelationUsageUncheckedTestCase,
)
from tests.unit.src.sqlbuild.adapters.clickhouse.helpers import (
    FakeQueryLogConnection,
    FakeQueryLogError,
    read_clickhouse_usage,
    usage_relation,
)

WINDOW_SECONDS: int = 7 * 86_400
READ_AT: datetime = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
EARLIER_READ_AT: datetime = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
ORDERS: tuple[RelationInfo, ...] = (usage_relation("mart", "old_orders"),)


@pytest.mark.parametrize(
    "test_case",
    (
        ClickHouseRelationUsageTestCase(
            description="reads per initial user add up and the latest read wins",
            relations=(("mart", "old_orders"), ("mart", "old_customers")),
            rows=(
                ("mart.old_orders", "svc_reporting", 10, int(READ_AT.timestamp())),
                ("mart.old_orders", "alice", 4, int(EARLIER_READ_AT.timestamp())),
                ("mart.old_orders", "", 1, int(EARLIER_READ_AT.timestamp())),
                ("mart.products", "bob", 3, int(READ_AT.timestamp())),
            ),
            expected_names_sql="IN ('mart.old_customers', 'mart.old_orders')",
            expected_usages=(
                ("old_orders", ("svc_reporting", "alice", "unknown user"), 15, READ_AT),
            ),
        ),
        ClickHouseRelationUsageTestCase(
            description="names keep their case and quotes are escaped",
            relations=(("Mart", "Old'Orders"),),
            rows=(
                ("Mart.Old'Orders", "alice", 1, int(READ_AT.timestamp())),
                ("mart.old'orders", "bob", 1, int(READ_AT.timestamp())),
            ),
            expected_names_sql="IN ('Mart.Old\\'Orders')",
            expected_usages=(("Old'Orders", ("alice",), 1, READ_AT),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_query_log_when_reading_usage_then_reads_match_candidates(
    test_case: ClickHouseRelationUsageTestCase,
) -> None:
    connection: FakeQueryLogConnection = FakeQueryLogConnection(rows=test_case.rows)

    report: RelationUsageReport = read_clickhouse_usage(
        connection=connection,
        relations=tuple(usage_relation(*relation) for relation in test_case.relations),
        window_seconds=WINDOW_SECONDS,
    )

    sql: str
    (sql,) = connection.queries
    assert report.checked
    assert test_case.expected_names_sql in sql
    assert tuple(
        (usage.name, usage.readers, usage.query_count, usage.last_read_at)
        for usage in report.usages
    ) == (test_case.expected_usages)
    assert all(usage.direct for usage in report.usages)


@pytest.mark.parametrize(
    "test_case",
    (
        ClickHouseRelationUsageQueryTestCase(
            description="finished reads and inserts of any table a query touched, once per query",
            window_seconds=WINDOW_SECONDS,
            expected_sql_fragments=(
                "FROM system.query_log ARRAY JOIN tables AS object_name",
                "initial_user AS user_name",
                "uniqExact(initial_query_id) AS query_count",
                "toUnixTimestamp(max(event_time)) AS last_read_at",
                f"event_date >= toDate(now() - toIntervalSecond({WINDOW_SECONDS}))",
                f"event_time >= now() - toIntervalSecond({WINDOW_SECONDS})",
                "type = 'QueryFinish'",
                "query_kind IN ('Select', 'Insert')",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_query_log_query_when_built_then_child_queries_count_once(
    test_case: ClickHouseRelationUsageQueryTestCase,
) -> None:
    connection: FakeQueryLogConnection = FakeQueryLogConnection()

    read_clickhouse_usage(
        connection=connection, relations=ORDERS, window_seconds=test_case.window_seconds
    )

    sql: str
    (sql,) = connection.queries
    assert all(fragment in sql for fragment in test_case.expected_sql_fragments)
    assert "is_initial_query" not in sql


@pytest.mark.parametrize(
    "test_case",
    (
        ClickHouseRelationUsageChunkTestCase(
            description="no candidates read nothing",
            relation_count=0,
            expected_query_names=(),
        ),
        ClickHouseRelationUsageChunkTestCase(
            description="a large candidate set is split into IN lists of at most 1,000 names",
            relation_count=2_001,
            expected_query_names=(1_000, 1_000, 1),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_many_candidates_when_reading_usage_then_names_are_chunked(
    test_case: ClickHouseRelationUsageChunkTestCase,
) -> None:
    connection: FakeQueryLogConnection = FakeQueryLogConnection()

    report: RelationUsageReport = read_clickhouse_usage(
        connection=connection,
        relations=tuple(
            usage_relation("mart", f"old_orders_{index:04d}")
            for index in range(test_case.relation_count)
        ),
        window_seconds=WINDOW_SECONDS,
    )

    assert report.checked
    assert tuple(sql.count("'mart.old_orders_") for sql in connection.queries) == (
        test_case.expected_query_names
    )


@pytest.mark.parametrize(
    "test_case",
    (
        ClickHouseRelationUsageUncheckedTestCase(
            description="no SELECT grant on system.query_log is not checked",
            log_queries=True,
            errors=FakeQueryLogError.raised(
                "Code: 497. DB::Exception: janitor: Not enough privileges. To execute this "
                "query, it's necessary to have the grant SELECT for at least one column on "
                "system.query_log. (ACCESS_DENIED)"
            ),
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
        ClickHouseRelationUsageUncheckedTestCase(
            description="a server without a query log table is not checked",
            log_queries=True,
            errors=FakeQueryLogError.raised(
                "Code: 60. DB::Exception: Table system.query_log does not exist. (UNKNOWN_TABLE)"
            ),
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
        ClickHouseRelationUsageUncheckedTestCase(
            description="query logging turned off is not checked",
            log_queries=False,
            errors=(),
            expected_report=RelationUsageReport(checked=False, reason=USAGE_LOGGING_OFF_REASON),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_no_query_log_when_reading_usage_then_usage_is_not_checked(
    test_case: ClickHouseRelationUsageUncheckedTestCase,
) -> None:
    connection: FakeQueryLogConnection = FakeQueryLogConnection(
        log_queries=test_case.log_queries,
        errors=test_case.errors,
    )

    report: RelationUsageReport = read_clickhouse_usage(
        connection=connection, relations=ORDERS, window_seconds=WINDOW_SECONDS
    )

    assert report == test_case.expected_report


@pytest.mark.parametrize(
    "test_case",
    (
        ClickHouseRelationUsageFailureTestCase(
            description="a timeout is a real error",
            error=FakeQueryLogError(
                "Code: 159. DB::Exception: Timeout exceeded. (TIMEOUT_EXCEEDED)"
            ),
            expected_error_match="TIMEOUT_EXCEEDED",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_other_query_log_failure_when_reading_usage_then_error_propagates(
    test_case: ClickHouseRelationUsageFailureTestCase,
) -> None:
    connection: FakeQueryLogConnection = FakeQueryLogConnection(errors=(test_case.error,))

    with pytest.raises(FakeQueryLogError, match=test_case.expected_error_match):
        read_clickhouse_usage(
            connection=connection, relations=ORDERS, window_seconds=WINDOW_SECONDS
        )


@pytest.mark.parametrize(
    "test_case",
    (
        ClickHouseRelationUsageReplicaTestCase(
            description="a single server reads every query",
            replicas=1,
            expected_notices=(),
        ),
        ClickHouseRelationUsageReplicaTestCase(
            description="other replicas of this server's shard are not read, and it says so",
            replicas=3,
            expected_notices=("usage read from this server only; other replicas not checked",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_replicas_when_reading_usage_then_other_replicas_are_noted(
    test_case: ClickHouseRelationUsageReplicaTestCase,
) -> None:
    connection: FakeQueryLogConnection = FakeQueryLogConnection(replicas=test_case.replicas)

    report: RelationUsageReport = read_clickhouse_usage(
        connection=connection, relations=ORDERS, window_seconds=WINDOW_SECONDS
    )

    assert report.checked
    assert report.notices == test_case.expected_notices


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
