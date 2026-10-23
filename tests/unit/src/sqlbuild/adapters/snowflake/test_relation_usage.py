"""Snowflake relation usage reads ACCOUNT_USAGE access history once per chunk of candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsageReport
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.snowflake._helpers.relation_usage import (
    CLONE_STATEMENT_PATTERN,
    SQLBUILD_QUERY_TAG_FRAGMENT,
    USAGE_UNAVAILABLE_REASON,
)
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeRelationUsageChunkTestCase,
    SnowflakeRelationUsageErrorTestCase,
    SnowflakeRelationUsageTestCase,
)

WINDOW_SECONDS: int = 7 * 86_400
READ_AT: datetime = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
EARLIER_READ_AT: datetime = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)


class _AccessHistoryError(Exception):
    def __init__(self, message: str, errno: int | None) -> None:
        super().__init__(message)
        self.errno: int | None = errno


@dataclass
class _Warehouse:
    """Answers CURRENT_DATABASE() and access-history reads, recording each query."""

    current_database: str | None = None
    access_rows: tuple[tuple[object, ...], ...] = ()
    error: Exception | None = None
    queries: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)


class _Cursor:
    def __init__(self, warehouse: _Warehouse) -> None:
        self.warehouse: _Warehouse = warehouse
        self.rows: list[tuple[object, ...]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        if sql == "SELECT CURRENT_DATABASE()":
            self.rows = [(self.warehouse.current_database,)]
            return
        self.warehouse.queries.append((sql, params))
        if self.warehouse.error is not None:
            raise self.warehouse.error
        names: set[object] = set(params)
        self.rows = [row for row in self.warehouse.access_rows if row[0] in names]

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, warehouse: _Warehouse) -> None:
        self.warehouse: _Warehouse = warehouse

    def cursor(self) -> _Cursor:
        return _Cursor(self.warehouse)


def _relation(database: str | None, schema: str, name: str) -> RelationInfo:
    return RelationInfo(database=database, schema=schema, name=name, relation_type="base table")


def _usage(*, connection: _Connection, relations: tuple[RelationInfo, ...]) -> RelationUsageReport:
    return SnowflakeAdapter().relation_usage(
        connection=connection, relations=relations, window_seconds=WINDOW_SECONDS
    )


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeRelationUsageTestCase(
            description="reads per user add up, readers rank by queries, the latest read wins",
            relations=(("analytics", "mart", "orders_daily"), ("analytics", "mart", "customers")),
            current_database=None,
            access_rows=(
                ("ANALYTICS.MART.ORDERS_DAILY", "SVC_REPORTING", 10, READ_AT),
                ("ANALYTICS.MART.ORDERS_DAILY", "ALICE", 4, EARLIER_READ_AT),
                ("ANALYTICS.MART.PRODUCTS", "BOB", 3, READ_AT),
            ),
            expected_object_names=("ANALYTICS.MART.CUSTOMERS", "ANALYTICS.MART.ORDERS_DAILY"),
            expected_usages=(("orders_daily", ("SVC_REPORTING", "ALICE"), 14, READ_AT),),
        ),
        SnowflakeRelationUsageTestCase(
            description="unqualified relations use the session database and names fold upper",
            relations=((None, "mart", "orders_daily"),),
            current_database="SHOP_DB",
            access_rows=(("SHOP_DB.MART.ORDERS_DAILY", "SVC_REPORTING", 2, READ_AT),),
            expected_object_names=("SHOP_DB.MART.ORDERS_DAILY",),
            expected_usages=(("orders_daily", ("SVC_REPORTING",), 2, READ_AT),),
        ),
        SnowflakeRelationUsageTestCase(
            description="names that need quoting match the quoted object name, case kept upper",
            relations=(("analytics", "mart", "order-lines"),),
            current_database=None,
            access_rows=(('ANALYTICS.MART."ORDER-LINES"', "ALICE", 1, READ_AT),),
            expected_object_names=('ANALYTICS.MART."ORDER-LINES"',),
            expected_usages=(("order-lines", ("ALICE",), 1, READ_AT),),
        ),
        SnowflakeRelationUsageTestCase(
            description="a mixed-case reader object does not match an unquoted relation",
            relations=(("analytics", "mart", "orders_daily"),),
            current_database=None,
            access_rows=(('ANALYTICS.MART."orders_daily"', "ALICE", 1, READ_AT),),
            expected_object_names=("ANALYTICS.MART.ORDERS_DAILY",),
            expected_usages=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_access_history_when_reading_usage_then_reads_match_candidates(
    test_case: SnowflakeRelationUsageTestCase,
) -> None:
    warehouse: _Warehouse = _Warehouse(
        current_database=test_case.current_database, access_rows=test_case.access_rows
    )

    report: RelationUsageReport = _usage(
        connection=_Connection(warehouse),
        relations=tuple(_relation(*relation) for relation in test_case.relations),
    )

    assert report.checked
    assert report.reason is None
    sql: str
    params: tuple[object, ...]
    ((sql, params),) = warehouse.queries
    assert params[1 : 1 + len(test_case.expected_object_names)] == (test_case.expected_object_names)
    assert "SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY" in sql
    assert "LATERAL FLATTEN(INPUT => history.direct_objects_accessed)" in sql
    assert tuple(
        (usage.name, usage.readers, usage.query_count, usage.last_read_at)
        for usage in report.usages
    ) == (test_case.expected_usages)


def test_given_access_history_query_when_built_then_sqlbuild_queries_and_clones_are_excluded() -> (
    None
):
    warehouse: _Warehouse = _Warehouse()

    _usage(
        connection=_Connection(warehouse),
        relations=(_relation("analytics", "mart", "orders_daily"),),
    )

    sql: str
    params: tuple[object, ...]
    ((sql, params),) = warehouse.queries
    assert params == (
        WINDOW_SECONDS,
        "ANALYTICS.MART.ORDERS_DAILY",
        WINDOW_SECONDS,
        SQLBUILD_QUERY_TAG_FRAGMENT,
        CLONE_STATEMENT_PATTERN,
    )
    assert SQLBUILD_QUERY_TAG_FRAGMENT == '"app":"sqlbuild"'
    assert "NOT EXISTS (SELECT 1 FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY AS query" in sql
    assert "CONTAINS(COALESCE(query.query_tag, ''), %s)" in sql
    assert "STARTSWITH(query.query_type, 'CREATE') AND REGEXP_LIKE(query.query_text, %s" in sql
    assert sql.count("DATEADD('second', -%s, CURRENT_TIMESTAMP())") == 2


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
    warehouse: _Warehouse = _Warehouse()

    report: RelationUsageReport = _usage(
        connection=_Connection(warehouse),
        relations=tuple(
            _relation("analytics", "mart", f"old_orders_{index:04d}")
            for index in range(test_case.relation_count)
        ),
    )

    assert report.checked
    assert tuple(len(params) - 4 for _, params in warehouse.queries) == (
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
        ),
        SnowflakeRelationUsageErrorTestCase(
            description="insufficient privileges are not checked",
            errno=3001,
            message="Insufficient privileges to operate on schema 'ACCOUNT_USAGE'",
        ),
        SnowflakeRelationUsageErrorTestCase(
            description="a privilege message without an error number is not checked",
            errno=None,
            message="SQL access control error: Insufficient privileges to operate on view",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_no_access_history_access_when_reading_usage_then_usage_is_not_checked(
    test_case: SnowflakeRelationUsageErrorTestCase,
) -> None:
    warehouse: _Warehouse = _Warehouse(
        error=_AccessHistoryError(test_case.message, test_case.errno)
    )

    report: RelationUsageReport = _usage(
        connection=_Connection(warehouse),
        relations=(_relation("analytics", "mart", "orders_daily"),),
    )

    assert report == RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON)


def test_given_other_access_history_failure_when_reading_usage_then_error_propagates() -> None:
    warehouse: _Warehouse = _Warehouse(error=_AccessHistoryError("SQL execution canceled", 604))

    with pytest.raises(_AccessHistoryError, match="canceled"):
        _usage(
            connection=_Connection(warehouse),
            relations=(_relation("analytics", "mart", "orders_daily"),),
        )


def test_given_other_adapter_when_reading_usage_then_it_reports_unsupported() -> None:
    report: RelationUsageReport = DuckDbAdapter().relation_usage(
        connection=object(),
        relations=(_relation("analytics", "mart", "orders_daily"),),
        window_seconds=WINDOW_SECONDS,
    )

    assert report == RelationUsageReport(checked=False, reason="unsupported adapter")


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
