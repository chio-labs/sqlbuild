from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import QueryResult, TableFreshnessMetadata
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.compiler.source_freshness.main.observation import observe_configured_source_freshness
from sqlbuild.compiler.source_freshness.models import SourceFreshnessObservation
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from tests.unit.src.sqlbuild.compiler.source_freshness.main._test_types import (
    SharedSourceFreshnessColumnSqlTestCase,
    SharedSourceFreshnessObservationErrorTestCase,
    SharedSourceFreshnessObservationTestCase,
)


class CapturingFreshnessMetadataDuckDbAdapter(DuckDbAdapter):
    def __init__(self, *, metadata_observed_at: datetime | None) -> None:
        super().__init__()
        self.metadata_observed_at: datetime | None = metadata_observed_at

    def supports_table_freshness_metadata(self) -> bool:
        return True

    def get_table_freshness_metadata(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> TableFreshnessMetadata:
        return TableFreshnessMetadata(
            data_version=datetime(2026, 1, 15, 12, 0, 0),
            value_kind="timestamp",
            observed_at=self.metadata_observed_at,
        )


class CapturingQueryDuckDbAdapter(DuckDbAdapter):
    captured_sql: str | None

    def __init__(self) -> None:
        super().__init__()
        self.captured_sql = None

    def query(self, connection: Any, sql: str, *, limit: int | None = 1000) -> QueryResult:
        self.captured_sql = sql
        return QueryResult(columns=("data_version",), rows=((1,),))


OBSERVED_AT_TEST_CASES: list[SharedSourceFreshnessObservationTestCase] = [
    SharedSourceFreshnessObservationTestCase(
        description="uses adapter metadata observed_at when present",
        adapter_observed_at=datetime(2026, 1, 15, 12, 1, 0),
        fallback_observed_at=datetime(2026, 1, 15, 12, 5, 0),
        expected_observed_at=datetime(2026, 1, 15, 12, 1, 0),
    ),
    SharedSourceFreshnessObservationTestCase(
        description="falls back to caller observed_at when adapter omits observed_at",
        adapter_observed_at=None,
        fallback_observed_at=datetime(2026, 1, 15, 12, 5, 0),
        expected_observed_at=datetime(2026, 1, 15, 12, 5, 0),
    ),
]

COLUMN_SQL_TEST_CASES: list[SharedSourceFreshnessColumnSqlTestCase] = [
    SharedSourceFreshnessColumnSqlTestCase(
        description="renders database schema table and filter for column freshness",
        source_database="warehouse",
        source_schema="raw",
        source_table="orders",
        expected_sql_fragment="FROM warehouse.raw.orders",
        freshness_filter="updated_at >= current_date - interval '2 days'",
        expected_filter_fragment="WHERE updated_at >= current_date - interval '2 days'",
    ),
    SharedSourceFreshnessColumnSqlTestCase(
        description="omits where clause when column freshness has no filter",
        source_database="warehouse",
        source_schema="raw",
        source_table="orders",
        expected_sql_fragment="FROM warehouse.raw.orders",
        unexpected_sql_fragment=" WHERE ",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    OBSERVED_AT_TEST_CASES,
    ids=[case.description for case in OBSERVED_AT_TEST_CASES],
)
def test_given_adapter_freshness_metadata_when_observing_then_uses_expected_observed_at(
    test_case: SharedSourceFreshnessObservationTestCase,
) -> None:
    adapter: CapturingFreshnessMetadataDuckDbAdapter = CapturingFreshnessMetadataDuckDbAdapter(
        metadata_observed_at=test_case.adapter_observed_at
    )
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        observation: SourceFreshnessObservation = observe_configured_source_freshness(
            adapter=adapter,
            connection=connection,
            source=SourceEntry(
                name="raw.orders",
                table="orders",
                freshness=SourceFreshnessConfig(strategy=SourceFreshnessStrategy.ADAPTER),
            ),
            observed_at=test_case.fallback_observed_at,
        )
    finally:
        adapter.close(connection)

    assert observation.observed_at == test_case.expected_observed_at


@pytest.mark.parametrize(
    "test_case",
    COLUMN_SQL_TEST_CASES,
    ids=[case.description for case in COLUMN_SQL_TEST_CASES],
)
def test_given_column_freshness_source_when_observing_then_renders_full_relation(
    test_case: SharedSourceFreshnessColumnSqlTestCase,
) -> None:
    adapter: CapturingQueryDuckDbAdapter = CapturingQueryDuckDbAdapter()
    observe_configured_source_freshness(
        adapter=adapter,
        connection=object(),
        source=SourceEntry(
            name="raw.orders",
            database=test_case.source_database,
            schema=test_case.source_schema,
            table=test_case.source_table,
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.COLUMN,
                value_kind=SourceFreshnessValueKind.INTEGER,
                column="batch_id",
                filter=test_case.freshness_filter,
            ),
        ),
        observed_at=datetime(2026, 1, 15, 12, 5, 0),
    )

    assert adapter.captured_sql is not None
    assert test_case.expected_sql_fragment in adapter.captured_sql
    assert (test_case.expected_filter_fragment or "") in adapter.captured_sql
    assert (test_case.unexpected_sql_fragment or "__not_present__") not in adapter.captured_sql


@pytest.mark.parametrize(
    "test_case",
    [
        SharedSourceFreshnessObservationErrorTestCase(
            description="column freshness rejects expression sources",
            expected_error_fragment="column freshness requires a physical table source",
        )
    ],
    ids=["column freshness rejects expression sources"],
)
def test_given_column_freshness_expression_source_when_observing_then_raises_clear_error(
    test_case: SharedSourceFreshnessObservationErrorTestCase,
) -> None:
    adapter: CapturingQueryDuckDbAdapter = CapturingQueryDuckDbAdapter()

    with pytest.raises(SourceFreshnessObservationError, match=test_case.expected_error_fragment):
        observe_configured_source_freshness(
            adapter=adapter,
            connection=object(),
            source=SourceEntry(
                name="raw.orders",
                expression="SELECT 1 AS id",
                freshness=SourceFreshnessConfig(
                    strategy=SourceFreshnessStrategy.COLUMN,
                    value_kind=SourceFreshnessValueKind.INTEGER,
                    column="batch_id",
                ),
            ),
            observed_at=datetime(2026, 1, 15, 12, 5, 0),
        )
