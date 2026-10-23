"""Databricks relation usage reads Unity Catalog table lineage once per chunk of candidates."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsageReport
from sqlbuild.adapters.databricks.constants import USAGE_UNAVAILABLE_REASON
from tests.unit.src.sqlbuild.adapters.databricks._test_types import (
    DatabricksRelationUsageChunkTestCase,
    DatabricksRelationUsageErrorTestCase,
    DatabricksRelationUsageFailureTestCase,
    DatabricksRelationUsageQueryTestCase,
    DatabricksRelationUsageTestCase,
)
from tests.unit.src.sqlbuild.adapters.databricks.helpers import (
    FakeLineageConnection,
    FakeLineageError,
    read_databricks_usage,
    usage_relation,
)

WINDOW_SECONDS: int = 7 * 86_400
READ_AT: datetime = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
EARLIER_READ_AT: datetime = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
ORDERS_DAILY: tuple[RelationInfo, ...] = (usage_relation("shop", "mart", "orders_daily"),)


@pytest.mark.parametrize(
    "test_case",
    (
        DatabricksRelationUsageTestCase(
            description="read events per user add up and names fold to lowercase",
            relations=(("Shop", "Mart", "orders_daily"), ("shop", "mart", "customers")),
            rows=(
                ("shop.mart.orders_daily", "svc-reporting@example.com", 10, READ_AT),
                ("shop.mart.orders_daily", "alice@example.com", 4, EARLIER_READ_AT),
                ("shop.mart.orders_daily", None, 1, EARLIER_READ_AT),
                ("shop.mart.products", "bob@example.com", 3, READ_AT),
            ),
            expected_object_names=("shop.mart.customers", "shop.mart.orders_daily"),
            expected_usages=(
                (
                    "orders_daily",
                    ("svc-reporting@example.com", "alice@example.com", "unknown user"),
                    15,
                    READ_AT,
                ),
            ),
        ),
        DatabricksRelationUsageTestCase(
            description="a relation without a catalog is not looked up",
            relations=((None, "mart", "orders_daily"), ("shop", "mart", "customers")),
            rows=(),
            expected_object_names=("shop.mart.customers",),
            expected_usages=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_lineage_when_reading_usage_then_reads_match_candidates(
    test_case: DatabricksRelationUsageTestCase,
) -> None:
    connection: FakeLineageConnection = FakeLineageConnection(rows=test_case.rows)

    report: RelationUsageReport = read_databricks_usage(
        connection=connection,
        relations=tuple(usage_relation(*relation) for relation in test_case.relations),
        window_seconds=WINDOW_SECONDS,
    )

    params: dict[str, object]
    ((_, params),) = connection.queries
    assert report.checked
    assert tuple(params.values())[1:] == test_case.expected_object_names
    assert tuple(
        (usage.name, usage.readers, usage.query_count, usage.last_read_at)
        for usage in report.usages
    ) == (test_case.expected_usages)


@pytest.mark.parametrize(
    "test_case",
    (
        DatabricksRelationUsageQueryTestCase(
            description="read events of source tables within the window, with named parameters",
            window_seconds=WINDOW_SECONDS,
            expected_params={"window_seconds": WINDOW_SECONDS, "name_0": "shop.mart.orders_daily"},
            expected_sql_fragments=(
                "FROM system.access.table_lineage",
                "lower(source_table_full_name) AS object_name",
                "created_by AS user_name",
                "COUNT(DISTINCT COALESCE(statement_id, event_id)) AS query_count",
                "MAX(event_time) AS last_read_at",
                "event_date >= DATE(TIMESTAMPADD(SECOND, -:window_seconds, current_timestamp()))",
                "lower(source_table_full_name) IN (:name_0)",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_lineage_query_when_built_then_parameters_are_named(
    test_case: DatabricksRelationUsageQueryTestCase,
) -> None:
    connection: FakeLineageConnection = FakeLineageConnection()

    read_databricks_usage(
        connection=connection, relations=ORDERS_DAILY, window_seconds=test_case.window_seconds
    )

    sql: str
    params: dict[str, object]
    ((sql, params),) = connection.queries
    assert params == test_case.expected_params
    assert all(fragment in sql for fragment in test_case.expected_sql_fragments)


@pytest.mark.parametrize(
    "test_case",
    (
        DatabricksRelationUsageChunkTestCase(
            description="no candidates read nothing",
            relation_count=0,
            expected_query_names=(),
        ),
        DatabricksRelationUsageChunkTestCase(
            description="a large candidate set is split into IN lists of at most 1,000 names",
            relation_count=2_001,
            expected_query_names=(1_000, 1_000, 1),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_many_candidates_when_reading_usage_then_names_are_chunked(
    test_case: DatabricksRelationUsageChunkTestCase,
) -> None:
    connection: FakeLineageConnection = FakeLineageConnection()

    report: RelationUsageReport = read_databricks_usage(
        connection=connection,
        relations=tuple(
            usage_relation("shop", "mart", f"old_orders_{index:04d}")
            for index in range(test_case.relation_count)
        ),
        window_seconds=WINDOW_SECONDS,
    )

    assert report.checked
    assert tuple(len(params) - 1 for _, params in connection.queries) == (
        test_case.expected_query_names
    )
    assert all(sql.count(":name_") == len(params) - 1 for sql, params in connection.queries)


@pytest.mark.parametrize(
    "test_case",
    (
        DatabricksRelationUsageErrorTestCase(
            description="missing permissions on the system schema are not checked",
            message="[INSUFFICIENT_PERMISSIONS] Insufficient privileges: User does not have "
            "USE SCHEMA on Schema 'system.access'.",
            sqlstate="42501",
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
        DatabricksRelationUsageErrorTestCase(
            description="a disabled access schema is not checked",
            message="[TABLE_OR_VIEW_NOT_FOUND] The table or view `system`.`access`.`table_lineage` "
            "cannot be found.",
            sqlstate=None,
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
        DatabricksRelationUsageErrorTestCase(
            description="a workspace without Unity Catalog is not checked",
            message="[UC_NOT_ENABLED] Unity Catalog is not enabled on this cluster.",
            sqlstate=None,
            expected_report=RelationUsageReport(checked=False, reason=USAGE_UNAVAILABLE_REASON),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_no_lineage_access_when_reading_usage_then_usage_is_not_checked(
    test_case: DatabricksRelationUsageErrorTestCase,
) -> None:
    connection: FakeLineageConnection = FakeLineageConnection(
        errors=(FakeLineageError(test_case.message, test_case.sqlstate),)
    )

    report: RelationUsageReport = read_databricks_usage(
        connection=connection, relations=ORDERS_DAILY, window_seconds=WINDOW_SECONDS
    )

    assert report == test_case.expected_report


@pytest.mark.parametrize(
    "test_case",
    (
        DatabricksRelationUsageFailureTestCase(
            description="a cancelled statement is a real error",
            message="[OPERATION_CANCELED] The statement was cancelled.",
            sqlstate="HY008",
            expected_error_match="OPERATION_CANCELED",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_other_lineage_failure_when_reading_usage_then_error_propagates(
    test_case: DatabricksRelationUsageFailureTestCase,
) -> None:
    connection: FakeLineageConnection = FakeLineageConnection(
        errors=(FakeLineageError(test_case.message, test_case.sqlstate),)
    )

    with pytest.raises(FakeLineageError, match=test_case.expected_error_match):
        read_databricks_usage(
            connection=connection, relations=ORDERS_DAILY, window_seconds=WINDOW_SECONDS
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
