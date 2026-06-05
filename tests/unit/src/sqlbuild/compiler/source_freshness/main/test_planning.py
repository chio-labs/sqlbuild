from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import TableFreshnessMetadata
from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.planning import (
    build_direct_source_freshness_planning_result,
)
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_record
from sqlbuild.compiler.source_freshness.models import (
    DirectSourceFreshnessPlanningResult,
    SourceFreshnessRecord,
)
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from tests.unit.src.sqlbuild.compiler.source_freshness.main._test_types import (
    DirectSourceFreshnessAdapterDefaultTestCase,
    DirectSourceFreshnessLagToleranceTestCase,
    DirectSourceFreshnessManagedSkipTestCase,
    DirectSourceFreshnessMultiSchemaTestCase,
    DirectSourceFreshnessPlanningErrorTestCase,
    DirectSourceFreshnessPlanningTestCase,
    DirectSourceFreshnessUnknownTestCase,
)
from tests.unit.src.sqlbuild.compiler.source_freshness.main.helpers import (
    write_optional_previous_record,
    write_previous_record_to_schema,
)

RENDER_QUALIFIED_NAME: Callable[..., str | None] = DuckDbAdapter().render_qualified_name
RENDER_FRAMEWORK_TYPE: Callable[[FrameworkType], str] = DuckDbAdapter().render_framework_type


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
            data_version=42,
            value_kind="integer",
            observed_at=datetime(2026, 1, 15, 12, 0, 0),
        )


PLANNING_COMPARISON_TEST_CASES: list[DirectSourceFreshnessPlanningTestCase] = [
    DirectSourceFreshnessPlanningTestCase(
        description="classifies first direct source freshness observation as changed",
        previous_data_version=None,
        current_query="SELECT 1 AS data_version",
        expected_changed_count=1,
        expected_unchanged_count=0,
    ),
    DirectSourceFreshnessPlanningTestCase(
        description="classifies matching previous direct source freshness as unchanged",
        previous_data_version="1",
        current_query="SELECT 1 AS data_version",
        expected_changed_count=0,
        expected_unchanged_count=1,
    ),
    DirectSourceFreshnessPlanningTestCase(
        description="classifies different previous direct source freshness as changed",
        previous_data_version="1",
        current_query="SELECT 2 AS data_version",
        expected_changed_count=1,
        expected_unchanged_count=0,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLANNING_COMPARISON_TEST_CASES,
    ids=[case.description for case in PLANNING_COMPARISON_TEST_CASES],
)
def test_given_direct_source_freshness_state_when_planning_then_classifies_hash_comparison(
    test_case: DirectSourceFreshnessPlanningTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        connection.execute("CREATE SCHEMA state_schema")
        source: SourceEntry = SourceEntry(
            name="raw.orders",
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.SQL,
                value_kind=SourceFreshnessValueKind.INTEGER,
                query=test_case.current_query,
            ),
        )
        write_optional_previous_record(
            adapter=adapter,
            connection=connection,
            render_qualified_name=RENDER_QUALIFIED_NAME,
            render_framework_type=RENDER_FRAMEWORK_TYPE,
            data_version=test_case.previous_data_version,
        )

        result: DirectSourceFreshnessPlanningResult = build_direct_source_freshness_planning_result(
            adapter=adapter,
            connection=connection,
            sources=(source,),
            state_database=None,
            state_schemas=("state_schema",),
            observed_at=datetime(2026, 1, 15, 12, 0, 0),
            run_id="planning",
            render_qualified_name=RENDER_QUALIFIED_NAME,
        )
    finally:
        adapter.close(connection)

    assert len(result.changed_identities) == test_case.expected_changed_count
    assert len(result.unchanged_identities) == test_case.expected_unchanged_count
    assert len(result.observed_records) == 1


LAG_TOLERANCE_TEST_CASES: tuple[DirectSourceFreshnessLagToleranceTestCase, ...] = (
    DirectSourceFreshnessLagToleranceTestCase(
        description="within timestamp lag tolerance",
        current_query="SELECT CAST('2026-01-15 12:05:00' AS TIMESTAMP) AS data_version",
        expected_changed_count=0,
        expected_unchanged_count=1,
    ),
    DirectSourceFreshnessLagToleranceTestCase(
        description="exactly at timestamp lag tolerance boundary",
        current_query="SELECT CAST('2026-01-15 12:10:00' AS TIMESTAMP) AS data_version",
        expected_changed_count=0,
        expected_unchanged_count=1,
    ),
    DirectSourceFreshnessLagToleranceTestCase(
        description="beyond timestamp lag tolerance",
        current_query="SELECT CAST('2026-01-15 12:11:00' AS TIMESTAMP) AS data_version",
        expected_changed_count=1,
        expected_unchanged_count=0,
    ),
    DirectSourceFreshnessLagToleranceTestCase(
        description="backwards timestamp movement is conservative",
        current_query="SELECT CAST('2026-01-15 11:59:00' AS TIMESTAMP) AS data_version",
        expected_changed_count=1,
        expected_unchanged_count=0,
    ),
)


@pytest.mark.parametrize(
    "test_case",
    LAG_TOLERANCE_TEST_CASES,
    ids=[case.description for case in LAG_TOLERANCE_TEST_CASES],
)
def test_given_timestamp_lag_tolerance_when_planning_then_classifies_tolerated_movement(
    test_case: DirectSourceFreshnessLagToleranceTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    previous_data_version: str = "2026-01-15T12:00:00"
    try:
        connection.execute("CREATE SCHEMA state_schema")
        write_source_freshness_record(
            connection=connection,
            execute=adapter.execute,
            database=None,
            schema="state_schema",
            record=SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema=None,
                target_name=None,
                run_id="previous",
                strategy=SourceFreshnessStrategy.SQL.value,
                value_kind=SourceFreshnessValueKind.TIMESTAMP.value,
                data_version=previous_data_version,
                data_version_hash=source_freshness_data_version_hash(
                    source_name="raw.orders",
                    strategy=SourceFreshnessStrategy.SQL,
                    value_kind=SourceFreshnessValueKind.TIMESTAMP,
                    data_version=previous_data_version,
                ),
                observed_at=datetime(2026, 1, 15, 12, 0, 0),
            ),
            render_qualified_name=RENDER_QUALIFIED_NAME,
            render_framework_type=RENDER_FRAMEWORK_TYPE,
        )

        result: DirectSourceFreshnessPlanningResult = build_direct_source_freshness_planning_result(
            adapter=adapter,
            connection=connection,
            sources=(
                SourceEntry(
                    name="raw.orders",
                    freshness=SourceFreshnessConfig(
                        strategy=SourceFreshnessStrategy.SQL,
                        value_kind=SourceFreshnessValueKind.TIMESTAMP,
                        query=test_case.current_query,
                        lag_tolerance="10m",
                    ),
                ),
            ),
            state_database=None,
            state_schemas=("state_schema",),
            observed_at=datetime(2026, 1, 15, 12, 30, 0),
            run_id="planning",
            render_qualified_name=RENDER_QUALIFIED_NAME,
        )
    finally:
        adapter.close(connection)

    assert len(result.changed_identities) == test_case.expected_changed_count
    assert len(result.unchanged_identities) == test_case.expected_unchanged_count


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceFreshnessUnknownTestCase(
            description="classifies unsupported default source freshness as unknown",
            expected_unknown_source_names=("raw.orders",),
        )
    ],
    ids=["classifies unsupported default source freshness as unknown"],
)
def test_given_unconfigured_source_without_adapter_metadata_when_planning_then_marks_unknown(
    test_case: DirectSourceFreshnessUnknownTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        result: DirectSourceFreshnessPlanningResult = build_direct_source_freshness_planning_result(
            adapter=adapter,
            connection=connection,
            sources=(SourceEntry(name="raw.orders", table="orders"),),
            state_database=None,
            state_schemas=("state_schema",),
            observed_at=datetime(2026, 1, 15, 12, 0, 0),
            run_id="planning",
            render_qualified_name=RENDER_QUALIFIED_NAME,
        )
    finally:
        adapter.close(connection)

    assert result.unknown_source_names == test_case.expected_unknown_source_names
    assert result.observed_records == ()


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceFreshnessPlanningErrorTestCase(
            description="explicit column freshness error propagates clearly",
            expected_error_fragment="column freshness requires a physical table source",
        )
    ],
    ids=["explicit column freshness error propagates clearly"],
)
def test_given_invalid_explicit_source_freshness_when_planning_then_raises_clear_error(
    test_case: DirectSourceFreshnessPlanningErrorTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        with pytest.raises(
            SourceFreshnessObservationError, match=test_case.expected_error_fragment
        ):
            build_direct_source_freshness_planning_result(
                adapter=adapter,
                connection=connection,
                sources=(
                    SourceEntry(
                        name="raw.orders",
                        expression="SELECT 1 AS id",
                        freshness=SourceFreshnessConfig(
                            strategy=SourceFreshnessStrategy.COLUMN,
                            value_kind=SourceFreshnessValueKind.INTEGER,
                            column="batch_id",
                        ),
                    ),
                ),
                state_database=None,
                state_schemas=("state_schema",),
                observed_at=datetime(2026, 1, 15, 12, 0, 0),
                run_id="planning",
                render_qualified_name=RENDER_QUALIFIED_NAME,
            )
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceFreshnessAdapterDefaultTestCase(
            description="adapter default freshness observes unconfigured physical source",
            expected_changed_count=1,
            expected_observed_count=1,
        )
    ],
    ids=["adapter default freshness observes unconfigured physical source"],
)
def test_given_adapter_metadata_support_when_planning_unconfigured_source_then_observes_default(
    test_case: DirectSourceFreshnessAdapterDefaultTestCase,
) -> None:
    adapter: FreshnessMetadataDuckDbAdapter = FreshnessMetadataDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        result: DirectSourceFreshnessPlanningResult = build_direct_source_freshness_planning_result(
            adapter=adapter,
            connection=connection,
            sources=(SourceEntry(name="raw.orders", schema="raw", table="orders"),),
            state_database=None,
            state_schemas=("state_schema",),
            observed_at=datetime(2026, 1, 15, 12, 5, 0),
            run_id="planning",
            render_qualified_name=RENDER_QUALIFIED_NAME,
        )
    finally:
        adapter.close(connection)

    assert len(result.changed_identities) == test_case.expected_changed_count
    assert len(result.observed_records) == test_case.expected_observed_count


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceFreshnessManagedSkipTestCase(
            description="managed sources are skipped during direct planning observation",
            expected_observed_count=0,
            expected_unknown_source_names=(),
        )
    ],
    ids=["managed sources are skipped during direct planning observation"],
)
def test_given_managed_source_when_planning_source_freshness_then_skips_observation(
    test_case: DirectSourceFreshnessManagedSkipTestCase,
) -> None:
    adapter: FreshnessMetadataDuckDbAdapter = FreshnessMetadataDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        result: DirectSourceFreshnessPlanningResult = build_direct_source_freshness_planning_result(
            adapter=adapter,
            connection=connection,
            sources=(SourceEntry(name="raw.orders", schema="raw", table="orders", managed=True),),
            state_database=None,
            state_schemas=("state_schema",),
            observed_at=datetime(2026, 1, 15, 12, 5, 0),
            run_id="planning",
            render_qualified_name=RENDER_QUALIFIED_NAME,
        )
    finally:
        adapter.close(connection)

    assert len(result.observed_records) == test_case.expected_observed_count
    assert result.unknown_source_names == test_case.expected_unknown_source_names


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceFreshnessMultiSchemaTestCase(
            description="reads previous direct source freshness across multiple state schemas",
            expected_previous_count=2,
            expected_unchanged_count=1,
        )
    ],
    ids=["reads previous direct source freshness across multiple state schemas"],
)
def test_given_multiple_state_schemas_when_planning_then_merges_previous_records(
    test_case: DirectSourceFreshnessMultiSchemaTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        connection.execute("CREATE SCHEMA state_a")
        connection.execute("CREATE SCHEMA state_b")
        write_previous_record_to_schema(
            adapter=adapter,
            connection=connection,
            render_qualified_name=RENDER_QUALIFIED_NAME,
            render_framework_type=RENDER_FRAMEWORK_TYPE,
            schema="state_a",
            source_name="raw.orders",
            data_version="1",
        )
        write_previous_record_to_schema(
            adapter=adapter,
            connection=connection,
            render_qualified_name=RENDER_QUALIFIED_NAME,
            render_framework_type=RENDER_FRAMEWORK_TYPE,
            schema="state_b",
            source_name="raw.customers",
            data_version="2",
        )
        result: DirectSourceFreshnessPlanningResult = build_direct_source_freshness_planning_result(
            adapter=adapter,
            connection=connection,
            sources=(
                SourceEntry(
                    name="raw.orders",
                    freshness=SourceFreshnessConfig(
                        strategy=SourceFreshnessStrategy.SQL,
                        value_kind=SourceFreshnessValueKind.INTEGER,
                        query="SELECT 1 AS data_version",
                    ),
                ),
            ),
            state_database=None,
            state_schemas=("state_a", "state_b"),
            observed_at=datetime(2026, 1, 15, 12, 5, 0),
            run_id="planning",
            render_qualified_name=RENDER_QUALIFIED_NAME,
        )
    finally:
        adapter.close(connection)

    assert len(result.previous_records) == test_case.expected_previous_count
    assert len(result.unchanged_identities) == test_case.expected_unchanged_count
