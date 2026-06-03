from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from sqlbuild.virtual.freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.virtual.freshness.helpers.observation import observe_configured_source_freshness
from sqlbuild.virtual.freshness.models import SourceFreshnessObservation
from tests.unit.src.sqlbuild.virtual.freshness._test_types import (
    SourceFreshnessObservationErrorTestCase,
    SourceFreshnessObservationTestCase,
)

TEST_CASES: list[SourceFreshnessObservationTestCase] = [
    SourceFreshnessObservationTestCase(
        description="observes max column data version",
        setup_sql=(
            "CREATE TABLE raw_orders (updated_at INTEGER)",
            "INSERT INTO raw_orders VALUES (1), (3), (2)",
        ),
        source_name="raw_orders",
        table="raw_orders",
        strategy="column",
        column="updated_at",
        value_kind="integer",
        expected_data_version=3,
    ),
    SourceFreshnessObservationTestCase(
        description="observes sql data version",
        setup_sql=(),
        source_name="raw_orders",
        table=None,
        strategy="sql",
        query="SELECT 'version-1' AS data_version",
        value_kind="string",
        expected_data_version="version-1",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_source_freshness_config_when_observing_then_returns_data_version(
    test_case: SourceFreshnessObservationTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    observed_at: datetime = datetime(2026, 1, 1, 12, 0, 0)
    try:
        statement: str
        for statement in test_case.setup_sql:
            adapter.execute(connection, statement)
        observation: SourceFreshnessObservation = observe_configured_source_freshness(
            adapter=adapter,
            connection=connection,
            source=SourceEntry(
                name=test_case.source_name,
                table=test_case.table,
                freshness=SourceFreshnessConfig(
                    strategy=SourceFreshnessStrategy(test_case.strategy),
                    value_kind=SourceFreshnessValueKind(test_case.value_kind),
                    column=test_case.column,
                    query=test_case.query,
                ),
            ),
            observed_at=observed_at,
        )
    finally:
        adapter.close(connection)

    assert observation.source_name == test_case.source_name
    assert observation.data_version == test_case.expected_data_version
    assert observation.value_kind == SourceFreshnessValueKind(test_case.value_kind)
    assert observation.observed_at == observed_at


ERROR_TEST_CASES: list[SourceFreshnessObservationErrorTestCase] = [
    SourceFreshnessObservationErrorTestCase(
        description="raises when sql freshness returns multiple columns",
        setup_sql=(),
        source_name="raw_orders",
        table=None,
        strategy="sql",
        query="SELECT 1 AS left_value, 2 AS right_value",
        value_kind="integer",
        expected_error_fragment="must return exactly one column",
    ),
    SourceFreshnessObservationErrorTestCase(
        description="raises when sql freshness returns zero rows",
        setup_sql=(),
        source_name="raw_orders",
        table=None,
        strategy="sql",
        query="SELECT 1 AS data_version WHERE FALSE",
        value_kind="integer",
        expected_error_fragment="must return exactly one row",
    ),
    SourceFreshnessObservationErrorTestCase(
        description="raises when sql freshness returns null",
        setup_sql=(),
        source_name="raw_orders",
        table=None,
        strategy="sql",
        query="SELECT NULL AS data_version",
        value_kind="integer",
        expected_error_fragment="data_version cannot be null",
    ),
    SourceFreshnessObservationErrorTestCase(
        description="raises when adapter metadata is unsupported",
        setup_sql=(),
        source_name="raw_orders",
        table="raw_orders",
        strategy="adapter",
        value_kind=None,
        expected_error_fragment="does not support table freshness metadata",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_source_freshness_result_when_observing_then_raises_clear_error(
    test_case: SourceFreshnessObservationErrorTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        statement: str
        for statement in test_case.setup_sql:
            adapter.execute(connection, statement)
        source: SourceEntry = SourceEntry(
            name=test_case.source_name,
            table=test_case.table,
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy(test_case.strategy),
                value_kind=(
                    None
                    if test_case.value_kind is None
                    else SourceFreshnessValueKind(test_case.value_kind)
                ),
                column=test_case.column,
                query=test_case.query,
            ),
        )
        with pytest.raises(
            SourceFreshnessObservationError, match=test_case.expected_error_fragment
        ):
            observe_configured_source_freshness(
                adapter=adapter,
                connection=connection,
                source=source,
                observed_at=datetime(2026, 1, 1, 12, 0, 0),
            )
    finally:
        adapter.close(connection)
