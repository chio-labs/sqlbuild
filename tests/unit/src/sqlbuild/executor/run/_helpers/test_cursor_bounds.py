from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import duckdb
import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run._helpers.validation.cursor_bounds import (
    resolve_runtime_cursor_bounds,
    substitute_cursor_sentinels,
)
from sqlbuild.executor.run.models import RuntimeCursorSpec
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    CursorSentinelSubstitutionErrorTestCase,
    MixedTemporalWatermarkTestCase,
    RuntimeCursorEndBoundTestCase,
    RuntimeCursorOverrideTestCase,
    RuntimeCursorPolicyTestCase,
    RuntimeCursorStartTestCase,
    RuntimeExistingTargetOverrideTestCase,
    RuntimeTargetMaxTestCase,
    RuntimeTargetProbeFailureTestCase,
    RuntimeWatermarkStatementTestCase,
)
from tests.unit.src.sqlbuild.executor.run._helpers.helpers import (
    FakeCursorAdapter,
    RecordingCursorAdapter,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorSentinelSubstitutionErrorTestCase(
            description="unresolved cursor intrinsic",
            sql="SELECT __cursor_start()",
            expected_error_fragment="unresolved cursor markers",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_bounds_when_substituting_then_rejects_unresolved_intrinsics(
    test_case: CursorSentinelSubstitutionErrorTestCase,
) -> None:
    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        substitute_cursor_sentinels(
            sql=test_case.sql,
            bounds=CursorBounds(start="1", end="2"),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeCursorStartTestCase(
            description="runtime timestamp bounds clamp to configured floor",
            target_max=None,
            upstream_min=datetime(2024, 1, 1, tzinfo=UTC),
            upstream_max=datetime(2024, 2, 1, tzinfo=UTC),
            cursor_type=CursorType.TIMESTAMP,
            warehouse_column_type="TIMESTAMPTZ",
            cursor_start="2024-01-15T00:00:00+00:00",
            expected_start="2024-01-15T00:00:00+00:00",
            expected_end="2024-02-01T00:00:01+00:00",
        ),
        RuntimeCursorStartTestCase(
            description="runtime integer bounds clamp to configured floor",
            target_max=None,
            upstream_min=50,
            upstream_max=200,
            cursor_type=CursorType.INTEGER,
            warehouse_column_type="INTEGER",
            cursor_start="100",
            expected_start="100",
            expected_end="201",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_cursor_start_when_resolving_bounds_then_applies_lower_floor(
    test_case: RuntimeCursorStartTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute(
        f"CREATE TABLE upstream_data (cursor_value {test_case.warehouse_column_type})"
    )
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_max])

    cursor_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter()),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=test_case.cursor_type,
            cursor_grain=None,
            cursor_start=test_case.cursor_start,
            cursor_input_relations=(
                CursorInputRelation(
                    relation="upstream_data",
                    cursor_column="cursor_value",
                ),
            ),
        ),
    )

    assert cursor_bounds is not None
    assert cursor_bounds.start == test_case.expected_start
    assert cursor_bounds.end == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeWatermarkStatementTestCase(
            description="first run reads standalone min and max in deterministic order",
            target_exists=False,
            expected_statements=(
                "SELECT MIN(cursor_value), MAX(cursor_value) FROM a_watermark",
                "SELECT MIN(cursor_value), MAX(cursor_value) FROM z_watermark",
            ),
            expected_bounds=CursorBounds(start="10", end="91"),
        ),
        RuntimeWatermarkStatementTestCase(
            description="existing target reads only standalone maxima and deduplicates inputs",
            target_exists=True,
            expected_statements=(
                "SELECT MAX(cursor_value) FROM target_data",
                "SELECT MAX(cursor_value) FROM a_watermark",
                "SELECT MAX(cursor_value) FROM z_watermark",
            ),
            expected_bounds=CursorBounds(start="50", end="91"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_multiple_physical_watermarks_when_resolving_then_reads_standalone_statements(
    test_case: RuntimeWatermarkStatementTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE a_watermark (cursor_value INTEGER)")
    connection.execute("INSERT INTO a_watermark VALUES (10), (90)")
    connection.execute("CREATE TABLE z_watermark (cursor_value INTEGER)")
    connection.execute("INSERT INTO z_watermark VALUES (20), (100)")
    connection.execute("CREATE TABLE target_data (cursor_value INTEGER)")
    connection.execute("INSERT INTO target_data VALUES (50)")
    adapter: RecordingCursorAdapter = RecordingCursorAdapter(
        target_relation_exists=test_case.target_exists
    )

    bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, adapter),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(relation="z_watermark", cursor_column="cursor_value"),
                CursorInputRelation(relation="a_watermark", cursor_column="cursor_value"),
                CursorInputRelation(relation="a_watermark", cursor_column="cursor_value"),
            ),
        ),
    )

    assert "UNION ALL" not in " ".join(adapter.statements)
    assert tuple(adapter.statements) == test_case.expected_statements
    assert bounds == test_case.expected_bounds


@pytest.mark.parametrize(
    "test_case",
    [
        MixedTemporalWatermarkTestCase(
            description="date and timestamp watermarks compare at common coarsest grain",
            expected_start="2024-01-01",
            expected_end="2024-02-02T00:00:00",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_date_and_timestamp_watermarks_when_resolving_then_normalizes_comparison(
    test_case: MixedTemporalWatermarkTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE date_watermark (cursor_value DATE)")
    connection.execute("INSERT INTO date_watermark VALUES ('2024-01-01'), ('2024-02-02')")
    connection.execute("CREATE TABLE timestamp_watermark (cursor_value TIMESTAMP)")
    connection.execute(
        "INSERT INTO timestamp_watermark VALUES ('2024-01-01 12:00:00'), ('2024-02-01 23:00:00')"
    )

    bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter()),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.HOUR,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(
                    relation="date_watermark",
                    cursor_column="cursor_value",
                    cursor_grain=CursorGrain.DAY,
                ),
                CursorInputRelation(
                    relation="timestamp_watermark",
                    cursor_column="cursor_value",
                    cursor_grain=CursorGrain.HOUR,
                ),
            ),
        ),
    )

    assert bounds is not None
    assert bounds.start == test_case.expected_start
    assert bounds.end == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeCursorEndBoundTestCase(
            description="date cursor with day grain advances the end bound past the final date",
            upstream_min=date(2014, 1, 1),
            upstream_max=date(2014, 12, 31),
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            warehouse_column_type="DATE",
            expected_start="2014-01-01",
            expected_end="2015-01-01",
        ),
        RuntimeCursorEndBoundTestCase(
            description="date cursor without a grain advances the end bound past the final date",
            upstream_min=date(2014, 1, 1),
            upstream_max=date(2014, 12, 31),
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            warehouse_column_type="DATE",
            expected_start="2014-01-01",
            expected_end="2015-01-01",
        ),
        RuntimeCursorEndBoundTestCase(
            description="decimal integer cursor advances the end bound past the final value",
            upstream_min=Decimal(50),
            upstream_max=Decimal(200),
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            warehouse_column_type="DECIMAL(38,0)",
            expected_start="50",
            expected_end="201",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_datetime_cursor_when_resolving_bounds_then_end_bound_includes_final_value(
    test_case: RuntimeCursorEndBoundTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute(
        f"CREATE TABLE upstream_data (cursor_value {test_case.warehouse_column_type})"
    )
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_max])

    cursor_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter()),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=test_case.cursor_type,
            cursor_grain=test_case.cursor_grain,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(
                    relation="upstream_data",
                    cursor_column="cursor_value",
                ),
            ),
        ),
    )

    assert cursor_bounds is not None
    assert cursor_bounds.start == test_case.expected_start
    assert cursor_bounds.end == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeCursorOverrideTestCase(
            description="end-cursor-ts override clamps a day-grain date range to the requested end",
            upstream_min=date(2014, 1, 1),
            upstream_max=date(2014, 12, 31),
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            warehouse_column_type="DATE",
            start_cursor_override=None,
            end_cursor_override="2014-03-30",
            expected_start="2014-01-01",
            expected_end="2014-03-31",
        ),
        RuntimeCursorOverrideTestCase(
            description="start-cursor-ts override raises the start floor above the upstream min",
            upstream_min=date(2014, 1, 1),
            upstream_max=date(2014, 12, 31),
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            warehouse_column_type="DATE",
            start_cursor_override="2014-02-01",
            end_cursor_override="2014-03-30",
            expected_start="2014-02-01",
            expected_end="2014-03-31",
        ),
        RuntimeCursorOverrideTestCase(
            description="end-cursor-ts override wider than the data never widens the window",
            upstream_min=date(2014, 1, 1),
            upstream_max=date(2014, 12, 31),
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            warehouse_column_type="DATE",
            start_cursor_override=None,
            end_cursor_override="2015-06-01",
            expected_start="2014-01-01",
            expected_end="2015-01-01",
        ),
        RuntimeCursorOverrideTestCase(
            description="integer end-cursor override clamps the exclusive upper bound",
            upstream_min=50,
            upstream_max=200,
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            warehouse_column_type="INTEGER",
            start_cursor_override="100",
            end_cursor_override="150",
            expected_start="100",
            expected_end="151",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_overrides_when_resolving_runtime_bounds_then_clamps_to_requested_window(
    test_case: RuntimeCursorOverrideTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute(
        f"CREATE TABLE upstream_data (cursor_value {test_case.warehouse_column_type})"
    )
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_max])

    cursor_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter()),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=test_case.cursor_type,
            cursor_grain=test_case.cursor_grain,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(
                    relation="upstream_data",
                    cursor_column="cursor_value",
                ),
            ),
            start_cursor_override=test_case.start_cursor_override,
            end_cursor_override=test_case.end_cursor_override,
        ),
    )

    assert cursor_bounds is not None
    assert cursor_bounds.start == test_case.expected_start
    assert cursor_bounds.end == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeExistingTargetOverrideTestCase(
            description="explicit historical replay replaces a newer target high-water mark",
            upstream_min=date(2014, 1, 1),
            upstream_max=date(2014, 12, 31),
            target_max=date(2014, 12, 31),
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            cursor_start="2014-01-01",
            start_cursor_override="2014-01-01",
            end_cursor_override="2014-03-30",
            warehouse_column_type="DATE",
            expected_bounds=CursorBounds(start="2014-01-01T00:00:00", end="2014-03-31"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_newer_target_when_resolving_explicit_replay_then_uses_requested_start(
    test_case: RuntimeExistingTargetOverrideTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute(
        f"CREATE TABLE upstream_data (cursor_value {test_case.warehouse_column_type})"
    )
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_max])
    connection.execute(f"CREATE TABLE target_data (cursor_value {test_case.warehouse_column_type})")
    connection.execute("INSERT INTO target_data VALUES (?)", [test_case.target_max])

    cursor_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter(target_relation_exists=True)),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=test_case.cursor_type,
            cursor_grain=test_case.cursor_grain,
            cursor_start=test_case.cursor_start,
            cursor_input_relations=(
                CursorInputRelation(
                    relation="upstream_data",
                    cursor_column="cursor_value",
                    cursor_grain=test_case.cursor_grain,
                    is_model_backed=True,
                ),
            ),
            start_cursor_override=test_case.start_cursor_override,
            end_cursor_override=test_case.end_cursor_override,
        ),
    )

    assert cursor_bounds == test_case.expected_bounds


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeTargetMaxTestCase(
            description="existing target relation seeds start from target max",
            target_rows=(80, 100),
            upstream_min=50,
            upstream_max=200,
            cursor_type=CursorType.INTEGER,
            expected_start="100",
            expected_end="201",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_target_relation_when_resolving_bounds_then_starts_from_target_max(
    test_case: RuntimeTargetMaxTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE upstream_data (cursor_value INTEGER)")
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_min])
    connection.execute("INSERT INTO upstream_data VALUES (?)", [test_case.upstream_max])
    connection.execute("CREATE TABLE target_data (cursor_value INTEGER)")
    target_row: object
    for target_row in test_case.target_rows:
        connection.execute("INSERT INTO target_data VALUES (?)", [target_row])

    cursor_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter(target_relation_exists=True)),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=test_case.cursor_type,
            cursor_grain=None,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(
                    relation="upstream_data",
                    cursor_column="cursor_value",
                ),
            ),
        ),
    )

    assert cursor_bounds is not None
    assert cursor_bounds.start == test_case.expected_start
    assert cursor_bounds.end == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeTargetProbeFailureTestCase(
            description="target max query failure propagates instead of widening the window",
            expected_error_type=duckdb.CatalogException,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_max_query_failure_when_resolving_bounds_then_propagates_error(
    test_case: RuntimeTargetProbeFailureTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE upstream_data (cursor_value INTEGER)")
    connection.execute("INSERT INTO upstream_data VALUES (50)")
    connection.execute("INSERT INTO upstream_data VALUES (200)")

    with pytest.raises(test_case.expected_error_type):
        resolve_runtime_cursor_bounds(
            adapter=cast(BaseAdapter, FakeCursorAdapter(target_relation_exists=True)),
            connection=connection,
            target_relation="target_data",
            target_database=None,
            target_schema=None,
            target_name="target_data",
            spec=RuntimeCursorSpec(
                cursor_column="cursor_value",
                cursor_type=CursorType.INTEGER,
                cursor_grain=None,
                cursor_start=None,
                cursor_input_relations=(
                    CursorInputRelation(
                        relation="upstream_data",
                        cursor_column="cursor_value",
                    ),
                ),
            ),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeCursorPolicyTestCase(
            description="multiple inputs use the slowest common watermark",
            expected_bounds=CursorBounds(start="10", end="101"),
        ),
        RuntimeCursorPolicyTestCase(
            description="an empty input has no common watermark",
            expected_bounds=None,
            slow_input_setup_sql="SELECT 1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_multiple_runtime_inputs_when_resolving_then_uses_common_watermark(
    test_case: RuntimeCursorPolicyTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE fast_input (cursor_value INTEGER)")
    connection.execute("INSERT INTO fast_input VALUES (10), (200)")
    connection.execute("CREATE TABLE slow_input (cursor_value INTEGER)")
    connection.execute(test_case.slow_input_setup_sql)

    bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter()),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(relation="fast_input", cursor_column="cursor_value"),
                CursorInputRelation(relation="slow_input", cursor_column="cursor_value"),
            ),
        ),
    )

    assert bounds == test_case.expected_bounds


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeCursorPolicyTestCase(
            description="applies lookback from target watermark",
            lookback="20s",
            expected_bounds=CursorBounds(start="80", end="201"),
        ),
        RuntimeCursorPolicyTestCase(
            description="applies bounded replay from exclusive end",
            backfill_duration="30s",
            expected_bounds=CursorBounds(start="171", end="201"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_replay_policy_when_resolving_then_matches_planner_policy(
    test_case: RuntimeCursorPolicyTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE upstream_data (cursor_value INTEGER)")
    connection.execute("INSERT INTO upstream_data VALUES (50), (200)")
    connection.execute("CREATE TABLE target_data (cursor_value INTEGER)")
    connection.execute("INSERT INTO target_data VALUES (100)")

    bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter(target_relation_exists=True)),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(relation="upstream_data", cursor_column="cursor_value"),
            ),
            lookback=test_case.lookback,
            backfill_duration=test_case.backfill_duration,
        ),
    )

    assert bounds == test_case.expected_bounds


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeCursorPolicyTestCase(
            description="full refresh ignores old destination watermark",
            read_destination_cursor=False,
            expected_bounds=CursorBounds(start="10", end="201"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_full_refresh_runtime_discovery_when_resolving_then_ignores_old_target(
    test_case: RuntimeCursorPolicyTestCase,
) -> None:
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE upstream_data (cursor_value INTEGER)")
    connection.execute("INSERT INTO upstream_data VALUES (10), (200)")
    connection.execute("CREATE TABLE target_data (cursor_value INTEGER)")
    connection.execute("INSERT INTO target_data VALUES (150)")

    bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=cast(BaseAdapter, FakeCursorAdapter(target_relation_exists=True)),
        connection=connection,
        target_relation="target_data",
        target_database=None,
        target_schema=None,
        target_name="target_data",
        spec=RuntimeCursorSpec(
            cursor_column="cursor_value",
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            cursor_start=None,
            cursor_input_relations=(
                CursorInputRelation(relation="upstream_data", cursor_column="cursor_value"),
            ),
            read_destination_cursor=test_case.read_destination_cursor,
        ),
    )

    assert bounds == test_case.expected_bounds
