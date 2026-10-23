"""Snowflake relation usage reads ACCOUNT_USAGE access history once per chunk of candidates."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsageReport
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.constants import (
    CLONE_STATEMENT_PATTERN,
    SQLBUILD_QUERY_TAG_FRAGMENT,
    USAGE_UNAVAILABLE_REASON,
)
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeCloneStatementTestCase,
    SnowflakeRelationUsageChainsUnfollowedTestCase,
    SnowflakeRelationUsageChunkTestCase,
    SnowflakeRelationUsageErrorTestCase,
    SnowflakeRelationUsageFailureTestCase,
    SnowflakeRelationUsageQueryTestCase,
    SnowflakeRelationUsageTestCase,
    SnowflakeRelationUsageViaTestCase,
    UnsupportedRelationUsageTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    FakeAccessHistoryError,
    FakeUsageWarehouse,
    direct_read,
    read_snowflake_usage,
    usage_relation,
)

WINDOW_SECONDS: int = 7 * 86_400
READ_AT: datetime = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
EARLIER_READ_AT: datetime = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
ORDERS_DAILY: tuple[RelationInfo, ...] = (usage_relation("analytics", "mart", "orders_daily"),)


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeRelationUsageTestCase(
            description="reads per user add up, readers rank by queries, the latest read wins",
            relations=(("analytics", "mart", "orders_daily"), ("analytics", "mart", "customers")),
            current_database=None,
            access_rows=(
                direct_read("ANALYTICS.MART.ORDERS_DAILY", "SVC_REPORTING", 10, READ_AT),
                direct_read("ANALYTICS.MART.ORDERS_DAILY", "ALICE", 4, EARLIER_READ_AT),
                direct_read("ANALYTICS.MART.PRODUCTS", "BOB", 3, READ_AT),
            ),
            expected_object_names=("ANALYTICS.MART.CUSTOMERS", "ANALYTICS.MART.ORDERS_DAILY"),
            expected_usages=(("orders_daily", ("SVC_REPORTING", "ALICE"), 14, READ_AT),),
        ),
        SnowflakeRelationUsageTestCase(
            description="unqualified relations use the session database and names fold upper",
            relations=((None, "mart", "orders_daily"),),
            current_database="SHOP_DB",
            access_rows=(direct_read("SHOP_DB.MART.ORDERS_DAILY", "SVC_REPORTING", 2, READ_AT),),
            expected_object_names=("SHOP_DB.MART.ORDERS_DAILY",),
            expected_usages=(("orders_daily", ("SVC_REPORTING",), 2, READ_AT),),
        ),
        SnowflakeRelationUsageTestCase(
            description="names that need quoting match the quoted object name, case kept upper",
            relations=(("analytics", "mart", "order-lines"),),
            current_database=None,
            access_rows=(direct_read('ANALYTICS.MART."ORDER-LINES"', "ALICE", 1, READ_AT),),
            expected_object_names=('ANALYTICS.MART."ORDER-LINES"',),
            expected_usages=(("order-lines", ("ALICE",), 1, READ_AT),),
        ),
        SnowflakeRelationUsageTestCase(
            description="a mixed-case reader object does not match an unquoted relation",
            relations=(("analytics", "mart", "orders_daily"),),
            current_database=None,
            access_rows=(direct_read('ANALYTICS.MART."orders_daily"', "ALICE", 1, READ_AT),),
            expected_object_names=("ANALYTICS.MART.ORDERS_DAILY",),
            expected_usages=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_access_history_when_reading_usage_then_reads_match_candidates(
    test_case: SnowflakeRelationUsageTestCase,
) -> None:
    warehouse: FakeUsageWarehouse = FakeUsageWarehouse(
        current_database=test_case.current_database, access_rows=test_case.access_rows
    )

    report: RelationUsageReport = read_snowflake_usage(
        warehouse=warehouse,
        relations=tuple(usage_relation(*relation) for relation in test_case.relations),
        window_seconds=WINDOW_SECONDS,
    )

    params: tuple[object, ...]
    ((_, params),) = warehouse.queries
    assert report.checked
    assert params[1 : 1 + len(test_case.expected_object_names)] == (test_case.expected_object_names)
    assert tuple(
        (usage.name, usage.readers, usage.query_count, usage.last_read_at)
        for usage in report.usages
    ) == (test_case.expected_usages)


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeRelationUsageQueryTestCase(
            description="one flattened access-history read leaves out SQLBuild queries and clones",
            window_seconds=WINDOW_SECONDS,
            expected_params=(
                WINDOW_SECONDS,
                "ANALYTICS.MART.ORDERS_DAILY",
                "ANALYTICS.MART.ORDERS_DAILY",
                WINDOW_SECONDS,
                '"app":"sqlbuild"',
                CLONE_STATEMENT_PATTERN,
            ),
            expected_sql_fragments=(
                "FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY",
                "LATERAL FLATTEN(INPUT => history.direct_objects_accessed) AS accessed",
                "LATERAL FLATTEN(INPUT => history.base_objects_accessed) AS accessed",
                "WHERE direct_read.query_id = base.query_id "
                "AND direct_read.object_name = base.object_name",
                "NOT EXISTS (SELECT 1 FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY AS query",
                "CONTAINS(COALESCE(query.query_tag, ''), %s)",
                "STARTSWITH(query.query_type, 'CREATE') AND REGEXP_LIKE(query.query_text, %s",
                "COUNT(DISTINCT reads.query_id) AS query_count",
                "BOOLOR_AGG(reads.direct) AS direct",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_access_history_query_when_built_then_sqlbuild_queries_and_clones_are_excluded(
    test_case: SnowflakeRelationUsageQueryTestCase,
) -> None:
    warehouse: FakeUsageWarehouse = FakeUsageWarehouse()

    read_snowflake_usage(
        warehouse=warehouse, relations=ORDERS_DAILY, window_seconds=test_case.window_seconds
    )

    sql: str
    params: tuple[object, ...]
    ((sql, params),) = warehouse.queries
    assert params == test_case.expected_params
    assert (SQLBUILD_QUERY_TAG_FRAGMENT, CLONE_STATEMENT_PATTERN) == (test_case.expected_params[4:])
    assert all(fragment in sql for fragment in test_case.expected_sql_fragments)


VIEW_DOMAINS: tuple[str, ...] = ("VIEW", "MATERIALIZED VIEW", "SECURE VIEW")


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeRelationUsageViaTestCase(
            description="a table read only through a view names the view; any direct read wins",
            relations=(
                ("analytics", "mart", "orders_base", "base table"),
                ("analytics", "mart", "customers", "base table"),
            ),
            access_rows=(
                (
                    "ANALYTICS.MART.ORDERS_BASE",
                    "ALICE",
                    3,
                    READ_AT,
                    False,
                    '[\n  "ANALYTICS.MART.ORDERS_V",\n  "REPORTING.MART.ORDERS_W"\n]',
                ),
                ("ANALYTICS.MART.CUSTOMERS", "ALICE", 2, READ_AT, False, '["ANALYTICS.MART.C_V"]'),
                direct_read("ANALYTICS.MART.CUSTOMERS", "BOB", 1, EARLIER_READ_AT),
            ),
            dependency_rows=(),
            expected_dependency_params=((*VIEW_DOMAINS, "ANALYTICS", "REPORTING"),),
            expected_usages=(
                ("customers", ("ALICE", "BOB"), 3, True, ()),
                (
                    "orders_base",
                    ("ALICE",),
                    3,
                    False,
                    ("analytics.mart.orders_v", "reporting.mart.orders_w"),
                ),
            ),
        ),
        SnowflakeRelationUsageViaTestCase(
            description="candidates behind an in-use candidate view are in use through it",
            relations=(
                ("analytics", "mart", "orders_v", "view"),
                ("analytics", "mart", "orders_v2", "view"),
                ("analytics", "mart", "orders", "base table"),
                ("analytics", "mart", "unread_v", "view"),
            ),
            access_rows=(
                direct_read("ANALYTICS.MART.ORDERS_V", "ALICE", 5, READ_AT),
                (
                    "ANALYTICS.MART.ORDERS",
                    "ALICE",
                    5,
                    READ_AT,
                    False,
                    '["ANALYTICS.MART.ORDERS_V"]',
                ),
            ),
            dependency_rows=(
                ("ANALYTICS.MART.ORDERS_V", "ANALYTICS.MART.ORDERS_V2"),
                ("ANALYTICS.MART.ORDERS_V2", "ANALYTICS.MART.ORDERS"),
                ("ANALYTICS.MART.UNREAD_V", "ANALYTICS.MART.ORDERS"),
                ("ANALYTICS.MART.ORDERS_V2", "ANALYTICS.MART.NOT_A_CANDIDATE"),
            ),
            expected_dependency_params=((*VIEW_DOMAINS, "ANALYTICS"),),
            expected_usages=(
                ("orders", ("ALICE",), 5, False, ("analytics.mart.orders_v",)),
                ("orders_v", ("ALICE",), 5, True, ()),
                ("orders_v2", ("ALICE",), 5, False, ("analytics.mart.orders_v",)),
            ),
        ),
        SnowflakeRelationUsageViaTestCase(
            description="a candidate view between a read non-candidate view and a table is in use",
            relations=(
                ("analytics", "mart", "orders_v2", "view"),
                ("analytics", "mart", "orders", "base table"),
            ),
            access_rows=(
                (
                    "ANALYTICS.MART.ORDERS",
                    "ALICE",
                    4,
                    READ_AT,
                    False,
                    '["REPORTING.MART.ORDERS_W"]',
                ),
            ),
            dependency_rows=(
                ("REPORTING.MART.ORDERS_W", "REPORTING.MART.ORDERS_HELPER"),
                ("REPORTING.MART.ORDERS_HELPER", "ANALYTICS.MART.ORDERS_V2"),
                ("ANALYTICS.MART.ORDERS_V2", "ANALYTICS.MART.ORDERS"),
            ),
            expected_dependency_params=((*VIEW_DOMAINS, "ANALYTICS", "REPORTING"),),
            expected_usages=(
                ("orders", ("ALICE",), 4, False, ("reporting.mart.orders_w",)),
                ("orders_v2", ("ALICE",), 4, False, ("reporting.mart.orders_w",)),
            ),
        ),
        SnowflakeRelationUsageViaTestCase(
            description="nothing read means no dependency query",
            relations=(("analytics", "mart", "orders_v2", "view"),),
            access_rows=(),
            dependency_rows=(("ANALYTICS.MART.ORDERS_V2", "ANALYTICS.MART.ORDERS"),),
            expected_dependency_params=(),
            expected_usages=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_view_reads_when_reading_usage_then_indirect_reads_name_their_views(
    test_case: SnowflakeRelationUsageViaTestCase,
) -> None:
    warehouse: FakeUsageWarehouse = FakeUsageWarehouse(
        access_rows=test_case.access_rows, dependency_rows=test_case.dependency_rows
    )

    report: RelationUsageReport = read_snowflake_usage(
        warehouse=warehouse,
        relations=tuple(usage_relation(*relation) for relation in test_case.relations),
        window_seconds=WINDOW_SECONDS,
    )

    assert report.checked
    assert tuple(params for _, params in warehouse.dependency_queries) == (
        test_case.expected_dependency_params
    )
    assert all(
        "referencing_object_domain IN (%s, %s, %s) AND referencing_database IN (" in sql
        for sql, _ in warehouse.dependency_queries
    )
    assert tuple(
        sorted(
            (usage.name, usage.readers, usage.query_count, usage.direct, usage.via)
            for usage in report.usages
        )
    ) == (test_case.expected_usages)


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeCloneStatementTestCase(
            description="a table clone",
            statement="CREATE TABLE analytics.mart.orders_copy CLONE analytics.mart.orders",
            expected_clone=True,
        ),
        SnowflakeCloneStatementTestCase(
            description="a replaced transient clone at a point in time",
            statement="create or replace transient table orders_copy clone orders "
            "at(offset => -60);",
            expected_clone=True,
        ),
        SnowflakeCloneStatementTestCase(
            description="a schema clone after leading comments",
            statement="-- nightly copy\n/* keep */\nCREATE SCHEMA mart_copy CLONE mart",
            expected_clone=True,
        ),
        SnowflakeCloneStatementTestCase(
            description="quoted names and a dynamic table",
            statement='CREATE DYNAMIC TABLE "Orders Copy" CLONE "Orders"',
            expected_clone=True,
        ),
        SnowflakeCloneStatementTestCase(
            description="a CTAS selecting a column named clone",
            statement="CREATE TABLE orders_copy AS SELECT clone FROM orders",
            expected_clone=False,
        ),
        SnowflakeCloneStatementTestCase(
            description="a view whose comment mentions a clone",
            statement="CREATE VIEW orders_v AS SELECT 1 AS clone_id -- see a CLONE b",
            expected_clone=False,
        ),
        SnowflakeCloneStatementTestCase(
            description="a CTAS with clone inside a string",
            statement="CREATE TABLE notes AS SELECT 'orders CLONE copy' AS note",
            expected_clone=False,
        ),
        SnowflakeCloneStatementTestCase(
            description="a select with a clone statement in a comment",
            statement="SELECT * FROM orders -- CREATE TABLE a CLONE b",
            expected_clone=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_statement_when_matching_clone_pattern_then_only_clones_match(
    test_case: SnowflakeCloneStatementTestCase,
) -> None:
    matched: bool = (
        re.fullmatch(CLONE_STATEMENT_PATTERN, test_case.statement, re.IGNORECASE | re.DOTALL)
        is not None
    )

    assert matched == test_case.expected_clone


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeRelationUsageChunkTestCase(
            description="no candidates read nothing",
            relation_count=0,
            expected_query_names=(),
        ),
        SnowflakeRelationUsageChunkTestCase(
            description="a large candidate set is split into IN lists of at most 1,000 names",
            relation_count=2_001,
            expected_query_names=(1_000, 1_000, 1),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_many_candidates_when_reading_usage_then_names_are_chunked(
    test_case: SnowflakeRelationUsageChunkTestCase,
) -> None:
    warehouse: FakeUsageWarehouse = FakeUsageWarehouse()

    report: RelationUsageReport = read_snowflake_usage(
        warehouse=warehouse,
        relations=tuple(
            usage_relation("analytics", "mart", f"old_orders_{index:04d}")
            for index in range(test_case.relation_count)
        ),
        window_seconds=WINDOW_SECONDS,
    )

    assert report.checked
    assert tuple((len(params) - 4) // 2 for _, params in warehouse.queries) == (
        test_case.expected_query_names
    )
    assert all(sql.count("%s") == len(params) for sql, params in warehouse.queries)


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeRelationUsageErrorTestCase(
            description="a missing view (no Enterprise edition or access) is not checked",
            errno=2003,
            message="Object 'SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY' does not exist or not "
            "authorized.",
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
        SnowflakeRelationUsageErrorTestCase(
            description="insufficient privileges are not checked",
            errno=3001,
            message="Insufficient privileges to operate on schema 'ACCOUNT_USAGE'",
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
        SnowflakeRelationUsageErrorTestCase(
            description="a privilege message without an error number is not checked",
            errno=None,
            message="SQL access control error: Insufficient privileges to operate on view",
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_no_access_history_access_when_reading_usage_then_usage_is_not_checked(
    test_case: SnowflakeRelationUsageErrorTestCase,
) -> None:
    warehouse: FakeUsageWarehouse = FakeUsageWarehouse(
        errors=(FakeAccessHistoryError(test_case.message, test_case.errno),)
    )

    report: RelationUsageReport = read_snowflake_usage(
        warehouse=warehouse, relations=ORDERS_DAILY, window_seconds=WINDOW_SECONDS
    )

    assert report == test_case.expected_report


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeRelationUsageChainsUnfollowedTestCase(
            description="no OBJECT_VIEWER keeps the reads and says view chains were not followed",
            errno=3001,
            message="Insufficient privileges to operate on view 'OBJECT_DEPENDENCIES'",
            expected_usages=(("orders_daily", ("ALICE",), 2),),
            expected_notices=("view chains not followed: grant SNOWFLAKE.OBJECT_VIEWER",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_no_dependency_access_when_reading_usage_then_reads_are_kept_with_notice(
    test_case: SnowflakeRelationUsageChainsUnfollowedTestCase,
) -> None:
    warehouse: FakeUsageWarehouse = FakeUsageWarehouse(
        access_rows=(direct_read("ANALYTICS.MART.ORDERS_DAILY", "ALICE", 2, READ_AT),),
        dependency_errors=(FakeAccessHistoryError(test_case.message, test_case.errno),),
    )

    report: RelationUsageReport = read_snowflake_usage(
        warehouse=warehouse, relations=ORDERS_DAILY, window_seconds=WINDOW_SECONDS
    )

    assert report.checked
    assert len(warehouse.dependency_queries) == 1
    assert tuple((usage.name, usage.readers, usage.query_count) for usage in report.usages) == (
        test_case.expected_usages
    )
    assert report.notices == test_case.expected_notices


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeRelationUsageFailureTestCase(
            description="a cancelled read is a real error",
            errno=604,
            message="SQL execution canceled",
            expected_error_match="canceled",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_other_access_history_failure_when_reading_usage_then_error_propagates(
    test_case: SnowflakeRelationUsageFailureTestCase,
) -> None:
    warehouse: FakeUsageWarehouse = FakeUsageWarehouse(
        errors=(FakeAccessHistoryError(test_case.message, test_case.errno),)
    )

    with pytest.raises(FakeAccessHistoryError, match=test_case.expected_error_match):
        read_snowflake_usage(
            warehouse=warehouse, relations=ORDERS_DAILY, window_seconds=WINDOW_SECONDS
        )


@pytest.mark.parametrize(
    "test_case",
    (
        UnsupportedRelationUsageTestCase(
            description="duckdb has no usage source",
            adapter=DuckDbAdapter(),
            expected_report=RelationUsageReport(checked=False, reason="unsupported adapter"),
        ),
        UnsupportedRelationUsageTestCase(
            description="postgres has no usage source",
            adapter=PostgresAdapter(),
            expected_report=RelationUsageReport(checked=False, reason="unsupported adapter"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_other_adapter_when_reading_usage_then_it_reports_unsupported(
    test_case: UnsupportedRelationUsageTestCase,
) -> None:
    report: RelationUsageReport = test_case.adapter.relation_usage(
        connection=object(), relations=ORDERS_DAILY, window_seconds=WINDOW_SECONDS
    )

    assert report == test_case.expected_report


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
