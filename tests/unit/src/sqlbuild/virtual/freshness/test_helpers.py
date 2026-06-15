from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import TableFreshnessMetadata
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.compiler.source_freshness.main.normalization import (
    normalize_source_freshness_data_version,
)
from sqlbuild.compiler.source_freshness.main.observation import observe_configured_source_freshness
from sqlbuild.compiler.source_freshness.models import SourceFreshnessObservation
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from sqlbuild.virtual.freshness.helpers.state import (
    source_freshness_record_from_observation,
)
from sqlbuild.virtual.freshness.main.runtime_observation import (
    observe_virtual_environment_source_freshness,
)
from sqlbuild.virtual.freshness.models import SourceFreshnessRuntimeResult
from sqlbuild.virtual.state.models import SourceFreshnessRecord
from tests.unit.src.sqlbuild.virtual.freshness._test_types import (
    SourceFreshnessObservationErrorTestCase,
    SourceFreshnessObservationTestCase,
    SourceFreshnessRuntimeLagToleranceTestCase,
    SourceFreshnessRuntimeTestCase,
    SourceFreshnessStateErrorTestCase,
    SourceFreshnessStateTestCase,
    UnsupportedTableFreshnessMetadataGuardTestCase,
)


class FreshnessMetadataDuckDbAdapter(DuckDbAdapter):
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
            data_version=datetime(2026, 1, 1, 12, 0, 0),
            value_kind="timestamp",
        )


class UnsupportedFreshnessMetadataDuckDbAdapter(DuckDbAdapter):
    metadata_requested: bool

    def __init__(self) -> None:
        super().__init__()
        self.metadata_requested = False

    def supports_table_freshness_metadata(self) -> bool:
        return False

    def get_table_freshness_metadata(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> TableFreshnessMetadata:
        self.metadata_requested = True
        return TableFreshnessMetadata(
            data_version=datetime(2026, 1, 1, 12, 0, 0),
            value_kind="timestamp",
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


@pytest.mark.parametrize(
    "test_case",
    [
        UnsupportedTableFreshnessMetadataGuardTestCase(
            description="unsupported adapter guard prevents metadata lookup",
            source_name="raw_orders",
            table="raw_orders",
            expected_error_fragment="does not support table freshness metadata",
            expected_metadata_requested=False,
        )
    ],
    ids=["unsupported adapter guard prevents metadata lookup"],
)
def test_given_adapter_freshness_is_unsupported_when_observing_then_metadata_is_not_requested(
    test_case: UnsupportedTableFreshnessMetadataGuardTestCase,
) -> None:
    adapter: UnsupportedFreshnessMetadataDuckDbAdapter = UnsupportedFreshnessMetadataDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        source: SourceEntry = SourceEntry(
            name=test_case.source_name,
            table=test_case.table,
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.ADAPTER,
                value_kind=None,
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

    assert adapter.metadata_requested is test_case.expected_metadata_requested


STATE_TEST_CASES: list[SourceFreshnessStateTestCase] = [
    SourceFreshnessStateTestCase(
        description="normalizes timestamp freshness value",
        source_name="raw.orders",
        strategy="column",
        value_kind="timestamp",
        data_version=datetime(2026, 1, 1, 12, 34, 56, tzinfo=UTC),
        observed_at=datetime(2026, 1, 1, 13, 0, 0),
        expected_data_version="2026-01-01T12:34:56+00:00",
        expected_hash_changes_with_observed_at=False,
    ),
    SourceFreshnessStateTestCase(
        description="normalizes integer freshness value",
        source_name="raw.orders",
        strategy="column",
        value_kind="integer",
        data_version=123,
        observed_at=datetime(2026, 1, 1, 13, 0, 0),
        expected_data_version="123",
        expected_hash_changes_with_observed_at=False,
    ),
    SourceFreshnessStateTestCase(
        description="preserves string freshness value",
        source_name="raw.orders",
        strategy="sql",
        value_kind="string",
        data_version="batch-001",
        observed_at=datetime(2026, 1, 1, 13, 0, 0),
        expected_data_version="batch-001",
        expected_hash_changes_with_observed_at=False,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    STATE_TEST_CASES,
    ids=[case.description for case in STATE_TEST_CASES],
)
def test_given_source_freshness_observation_when_building_state_record_then_hashes_value(
    test_case: SourceFreshnessStateTestCase,
) -> None:
    observation: SourceFreshnessObservation = SourceFreshnessObservation(
        source_name=test_case.source_name,
        strategy=SourceFreshnessStrategy(test_case.strategy),
        data_version=test_case.data_version,
        value_kind=SourceFreshnessValueKind(test_case.value_kind),
        observed_at=test_case.observed_at,
    )

    record: SourceFreshnessRecord = source_freshness_record_from_observation(
        observation,
        virtual_environment_name="dev",
    )
    record_with_later_observed_at: SourceFreshnessRecord = source_freshness_record_from_observation(
        SourceFreshnessObservation(
            source_name=test_case.source_name,
            strategy=SourceFreshnessStrategy(test_case.strategy),
            data_version=test_case.data_version,
            value_kind=SourceFreshnessValueKind(test_case.value_kind),
            observed_at=datetime(2026, 1, 2, 13, 0, 0),
        ),
        virtual_environment_name="dev",
    )

    assert record.virtual_environment_name == "dev"
    assert record.source_name == test_case.source_name
    assert record.strategy == test_case.strategy
    assert record.value_kind == test_case.value_kind
    assert record.data_version == test_case.expected_data_version
    assert record.data_version_hash == record_with_later_observed_at.data_version_hash
    assert test_case.expected_hash_changes_with_observed_at is False


STATE_ERROR_TEST_CASES: list[SourceFreshnessStateErrorTestCase] = [
    SourceFreshnessStateErrorTestCase(
        description="rejects non datetime timestamp value",
        value_kind="timestamp",
        data_version="2026-01-01T12:00:00Z",
        expected_error_fragment="must be datetime values",
    ),
    SourceFreshnessStateErrorTestCase(
        description="rejects bool integer value",
        value_kind="integer",
        data_version=True,
        expected_error_fragment="must be integer values",
    ),
    SourceFreshnessStateErrorTestCase(
        description="rejects non integer value",
        value_kind="integer",
        data_version="123",
        expected_error_fragment="must be integer values",
    ),
    SourceFreshnessStateErrorTestCase(
        description="rejects non string value",
        value_kind="string",
        data_version=123,
        expected_error_fragment="must be string values",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    STATE_ERROR_TEST_CASES,
    ids=[case.description for case in STATE_ERROR_TEST_CASES],
)
def test_given_invalid_source_freshness_value_when_normalizing_then_raises_clear_error(
    test_case: SourceFreshnessStateErrorTestCase,
) -> None:
    with pytest.raises(SourceFreshnessObservationError, match=test_case.expected_error_fragment):
        normalize_source_freshness_data_version(
            value=test_case.data_version,
            value_kind=SourceFreshnessValueKind(test_case.value_kind),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessRuntimeTestCase(
            description="observes explicit config before adapter default and tracks unknowns",
            expected_record_sources=("raw.customers", "raw.orders"),
            expected_unknown_sources=("raw.unknown",),
            expected_preserved_sources=(),
            expected_generated_sources=(),
        )
    ],
    ids=["observes explicit config before adapter default and tracks unknowns"],
)
def test_given_unmanaged_sources_when_observing_runtime_freshness_then_applies_precedence(
    test_case: SourceFreshnessRuntimeTestCase,
) -> None:
    adapter: FreshnessMetadataDuckDbAdapter = FreshnessMetadataDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, "CREATE TABLE raw_orders (batch_id INTEGER)")
        adapter.execute(connection, "INSERT INTO raw_orders VALUES (7)")

        result: SourceFreshnessRuntimeResult = observe_virtual_environment_source_freshness(
            adapter=adapter,
            connection=connection,
            sources=(
                SourceEntry(
                    name="raw.orders",
                    table="raw_orders",
                    freshness=SourceFreshnessConfig(
                        strategy=SourceFreshnessStrategy.COLUMN,
                        value_kind=SourceFreshnessValueKind.INTEGER,
                        column="batch_id",
                    ),
                ),
                SourceEntry(name="raw.customers", table="raw_customers"),
                SourceEntry(name="raw.unknown", expression="SELECT 1 AS id"),
            ),
            virtual_environment_name="dev",
            observed_at=datetime(2026, 1, 1, 13, 0, 0),
        )
    finally:
        adapter.close(connection)

    records_by_source: dict[str, SourceFreshnessRecord] = {
        record.source_name: record for record in result.records
    }
    assert tuple(records_by_source) == test_case.expected_record_sources
    assert result.unknown_source_names == test_case.expected_unknown_sources
    assert result.preserved_source_names == test_case.expected_preserved_sources
    assert result.generated_source_names == test_case.expected_generated_sources
    assert records_by_source["raw.orders"].strategy == "column"
    assert records_by_source["raw.orders"].data_version == "7"
    assert records_by_source["raw.customers"].strategy == "adapter"
    assert records_by_source["raw.customers"].data_version == "2026-01-01T12:00:00"


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessRuntimeTestCase(
            description="preserves soft skipped source and generates load version",
            expected_record_sources=("raw.inventory", "raw.orders"),
            expected_unknown_sources=("raw.customers",),
            expected_preserved_sources=("raw.orders",),
            expected_generated_sources=("raw.inventory",),
        )
    ],
    ids=["preserves soft skipped source and generates load version"],
)
def test_given_managed_loader_results_when_observing_freshness_then_applies_loader_semantics(
    test_case: SourceFreshnessRuntimeTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    previous_record: SourceFreshnessRecord = SourceFreshnessRecord(
        virtual_environment_name="dev",
        source_name="raw.orders",
        strategy="column",
        value_kind="integer",
        data_version="10",
        data_version_hash="previous-hash",
        observed_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    try:
        result: SourceFreshnessRuntimeResult = observe_virtual_environment_source_freshness(
            adapter=adapter,
            connection=connection,
            sources=(
                SourceEntry(name="raw.orders", table="raw_orders", managed=True),
                SourceEntry(name="raw.inventory", table="raw_inventory", managed=True),
                SourceEntry(name="raw.customers", table="raw_customers", managed=True),
            ),
            virtual_environment_name="dev",
            observed_at=datetime(2026, 1, 2, 12, 0, 0),
            run_id="run-123",
            previous_records=(previous_record,),
            load_results=(
                LoadExecutionResult(
                    source_name="raw.orders",
                    loader_name="raw.orders",
                    status=ExecutionStatus.SKIPPED,
                    target="raw_orders",
                    skip_mode=SkipMode.SOFT,
                ),
                LoadExecutionResult(
                    source_name="raw.inventory",
                    loader_name="raw.inventory",
                    status=ExecutionStatus.SUCCESS,
                    target="raw_inventory",
                ),
                LoadExecutionResult(
                    source_name="raw.customers",
                    loader_name="raw.customers",
                    status=ExecutionStatus.SKIPPED,
                    target="raw_customers",
                    skip_mode=SkipMode.HARD,
                ),
            ),
        )
    finally:
        adapter.close(connection)

    records_by_source: dict[str, SourceFreshnessRecord] = {
        record.source_name: record for record in result.records
    }
    assert tuple(records_by_source) == test_case.expected_record_sources
    assert result.unknown_source_names == test_case.expected_unknown_sources
    assert result.preserved_source_names == test_case.expected_preserved_sources
    assert result.generated_source_names == test_case.expected_generated_sources
    assert records_by_source["raw.orders"] == previous_record
    assert records_by_source["raw.inventory"].strategy == "loader"
    assert records_by_source["raw.inventory"].data_version == "run-123"


RUNTIME_LAG_TOLERANCE_TEST_CASES: tuple[SourceFreshnessRuntimeLagToleranceTestCase, ...] = (
    SourceFreshnessRuntimeLagToleranceTestCase(
        description="preserves previous within lag tolerance",
        current_data_version="2026-01-01T12:05:00",
        expected_record_data_version="2026-01-01T12:00:00",
    ),
    SourceFreshnessRuntimeLagToleranceTestCase(
        description="preserves previous at lag tolerance boundary",
        current_data_version="2026-01-01T12:10:00",
        expected_record_data_version="2026-01-01T12:00:00",
    ),
    SourceFreshnessRuntimeLagToleranceTestCase(
        description="advances beyond lag tolerance",
        current_data_version="2026-01-01T12:11:00",
        expected_record_data_version="2026-01-01T12:11:00",
    ),
    SourceFreshnessRuntimeLagToleranceTestCase(
        description="advances on backwards timestamp movement",
        current_data_version="2026-01-01T11:59:00",
        expected_record_data_version="2026-01-01T11:59:00",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    RUNTIME_LAG_TOLERANCE_TEST_CASES,
    ids=[case.description for case in RUNTIME_LAG_TOLERANCE_TEST_CASES],
)
def test_given_virtual_runtime_lag_tolerance_when_observing_then_preserves_baseline(
    test_case: SourceFreshnessRuntimeLagToleranceTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    previous_record: SourceFreshnessRecord = SourceFreshnessRecord(
        virtual_environment_name="dev",
        source_name="raw.orders",
        strategy=SourceFreshnessStrategy.SQL.value,
        value_kind=SourceFreshnessValueKind.TIMESTAMP.value,
        data_version="2026-01-01T12:00:00",
        data_version_hash="previous-hash",
        observed_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    try:
        result: SourceFreshnessRuntimeResult = observe_virtual_environment_source_freshness(
            adapter=adapter,
            connection=connection,
            sources=(
                SourceEntry(
                    name="raw.orders",
                    freshness=SourceFreshnessConfig(
                        strategy=SourceFreshnessStrategy.SQL,
                        value_kind=SourceFreshnessValueKind.TIMESTAMP,
                        query=f"SELECT CAST('{test_case.current_data_version}' AS TIMESTAMP)",
                        lag_tolerance="10m",
                    ),
                ),
            ),
            virtual_environment_name="dev",
            observed_at=datetime(2026, 1, 1, 12, 30, 0),
            previous_records=(previous_record,),
        )
    finally:
        adapter.close(connection)

    assert result.records[0].data_version == test_case.expected_record_data_version
