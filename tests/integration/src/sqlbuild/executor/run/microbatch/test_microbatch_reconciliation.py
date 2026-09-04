"""Integration coverage for grouped microbatch reconciliation row counts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.planner._helpers.resolve.cursor import compute_cursor_bounds
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CursorBounds,
    ModelCursorSnapshot,
    ModelPlanEntry,
)
from sqlbuild.compiler.planner.types import BackfillAction, CursorWatermarkMode
from sqlbuild.cursor_algebra.main.sentinel_to_token import sentinel_to_token
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run._helpers.materializations.microbatch import (
    _clamp_intervals_to_model_domain,
    _count_unaccounted_intervals,
    _MicrobatchHistoryContext,
    _MicrobatchPlan,
    _plan_microbatch_windows,
    _serial_trailing_recovery_only,
    execute_microbatch_entry,
)
from sqlbuild.executor.run._helpers.validation.cursor_bounds import resolve_runtime_cursor_bounds
from sqlbuild.executor.run.models import (
    MicrobatchLifecycleState,
    MicrobatchTargets,
    ModelExecutionResult,
    ModelMaterializationContext,
    RuntimeCursorInputRelation,
    RuntimeCursorSpec,
)
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.microbatches.models import (
    MicrobatchEvent,
    MicrobatchInterval,
    MicrobatchScope,
    MicrobatchWriteResult,
)
from sqlbuild.spec.contracts.types import MicrobatchLimitAction
from tests.integration.src.sqlbuild.executor.run.microbatch._test_types import (
    MicrobatchBehaviorTestCase,
    MicrobatchReconciliationChunkTestCase,
    PlannerRuntimeCursorParityTestCase,
    RuntimeWatermarkGrainTestCase,
)
from tests.integration.src.sqlbuild.executor.run.microbatch.helpers import (
    build_integer_reconciliation_plan_entry,
    resolve_nonempty_terminal_bounds,
)
from tests.unit.src.sqlbuild.microbatches.helpers import SCOPE, completion_event


class _CountTrackingDuckDbAdapter(DuckDbAdapter):
    def __init__(self) -> None:
        self.count_sqls: list[str] = []

    def _execute(self, *, connection: Any, sql: str) -> Any:
        if "AS __sqb_count_" in sql:
            self.count_sqls.append(sql)
        return super()._execute(connection=connection, sql=sql)


class _RecordingEventStore:
    def __init__(self) -> None:
        self.writes: list[MicrobatchEvent] = []

    def write(self, event: MicrobatchEvent) -> None:
        self.writes.append(event)

    def write_many(self, events: tuple[MicrobatchEvent, ...]) -> MicrobatchWriteResult:
        self.writes.extend(events)
        return MicrobatchWriteResult(total=len(events), inserted=len(events), already_existing=0)

    def read_scope_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        return ()

    def read_model_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        return ()


@pytest.mark.parametrize(
    "test_case",
    (
        PlannerRuntimeCursorParityTestCase(
            description="monthly all watermark floors physical maximum",
            watermark_mode=CursorWatermarkMode.ALL,
            expected_end="2026-08-01T00:00:00",
        ),
        PlannerRuntimeCursorParityTestCase(
            description="monthly any watermark floors physical maximum",
            watermark_mode=CursorWatermarkMode.ANY,
            expected_end="2026-08-01T00:00:00",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_monthly_physical_maximum_when_planning_and_resolving_then_availability_ends_match(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: PlannerRuntimeCursorParityTestCase,
) -> None:
    physical_maximum: str = "2026-07-15 12:00:00"
    planner_bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=ModelCursorSnapshot(
            target_max=None,
            upstream_mins=("2026-07-01 00:00:00",),
            upstream_maxes=(physical_maximum,),
            cursor_watermark_mode=test_case.watermark_mode,
        ),
        cursor_type="timestamp",
        cursor_start="2026-07-01",
        lookback=None,
        backfill_duration=None,
        start_cursor_override=None,
        end_cursor_override=None,
        is_microbatch=False,
        cursor_grain="month",
    )
    connection.execute("CREATE TABLE main.target_events (event_time TIMESTAMP)")
    connection.execute("CREATE TABLE main.producer_events (event_time TIMESTAMP)")
    connection.execute("INSERT INTO main.producer_events VALUES (?)", [physical_maximum])

    runtime_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=adapter,
        connection=connection,
        target_relation="main.target_events",
        target_database=None,
        target_schema="main",
        target_name="target_events",
        spec=RuntimeCursorSpec(
            cursor_column="event_time",
            cursor_type="timestamp",
            cursor_grain="month",
            cursor_start="2026-07-01",
            cursor_input_relations=(
                RuntimeCursorInputRelation(
                    relation="main.producer_events",
                    cursor_column="event_time",
                    cursor_grain="month",
                ),
            ),
            cursor_watermark_mode=test_case.watermark_mode,
            microbatch_strategy="watermark",
        ),
    )

    assert planner_bounds is not None
    assert runtime_bounds is not None
    assert planner_bounds.end == runtime_bounds.end
    assert sentinel_to_token(sentinel=planner_bounds.end) == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    (
        RuntimeWatermarkGrainTestCase(
            description="midmonth producer maximum exposes the next monthly boundary",
            consumer_grain="hour",
            producer_grain="month",
            producer_maximum="2026-04-15 12:00:00",
            expected_end="2026-05-01T00:00:00",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_watermark_model_with_coarse_producer_when_resolving_then_producer_grain_sets_availability(
    test_case: RuntimeWatermarkGrainTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute("CREATE TABLE main.target_events (event_time TIMESTAMP)")
    connection.execute("CREATE TABLE main.producer_events (event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO main.producer_events VALUES (?)", parameters=[test_case.producer_maximum]
    )

    bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=adapter,
        connection=connection,
        target_relation="main.target_events",
        target_database=None,
        target_schema="main",
        target_name="target_events",
        spec=RuntimeCursorSpec(
            cursor_column="event_time",
            cursor_type="timestamp",
            cursor_grain=test_case.consumer_grain,
            cursor_start="2026-04-01",
            cursor_input_relations=(
                RuntimeCursorInputRelation(
                    relation="main.producer_events",
                    cursor_column="event_time",
                    cursor_grain=test_case.producer_grain,
                ),
            ),
            cursor_watermark_mode="all",
            microbatch_strategy="watermark",
        ),
    )

    assert bounds is not None
    assert sentinel_to_token(sentinel=bounds.end) == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchReconciliationChunkTestCase(
            description="one full chunk uses one grouped query",
            interval_count=100,
            occupied_values=(0, 99),
            expected_query_count=1,
        ),
        MicrobatchReconciliationChunkTestCase(
            description="one interval beyond boundary starts a second grouped query",
            interval_count=101,
            occupied_values=(99, 100),
            expected_query_count=2,
        ),
        MicrobatchReconciliationChunkTestCase(
            description="two full chunks plus one interval use three grouped queries",
            interval_count=201,
            occupied_values=(99, 100, 199, 200),
            expected_query_count=3,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_many_unaccounted_intervals_when_counting_then_queries_are_chunked_without_n_plus_one(
    test_case: MicrobatchReconciliationChunkTestCase,
) -> None:
    adapter: _CountTrackingDuckDbAdapter = _CountTrackingDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        connection.execute("CREATE TABLE main.orders (id INTEGER)")
        values_sql: str = ", ".join(f"({value})" for value in test_case.occupied_values)
        connection.execute(f"INSERT INTO main.orders VALUES {values_sql}")
        context: ModelMaterializationContext = ModelMaterializationContext(
            entry=build_integer_reconciliation_plan_entry(),
            adapter=adapter,
            connection=connection,
            model_locations={},
            seed_locations={},
            source_map={},
            model_audits=(),
            run_id="reconciliation-chunks",
            query_change_tracking=False,
        )
        intervals: tuple[MicrobatchInterval, ...] = tuple(
            MicrobatchInterval(start=str(value), end=str(value + 1))
            for value in range(test_case.interval_count)
        )

        result: dict[tuple[str, str], int] | ModelExecutionResult = _count_unaccounted_intervals(
            context=context,
            state=MicrobatchLifecycleState(
                warnings=[],
                audit_results=[],
                hook_results=[],
                statement_recorder=StatementRecorder(),
            ),
            targets=MicrobatchTargets(
                target_database=None,
                target_schema="main",
                target_table="orders",
                target_qualified="main.orders",
                delta_table="orders__delta",
                delta_qualified="main.orders__delta",
            ),
            intervals=intervals,
        )
    finally:
        adapter.close(connection)

    assert isinstance(result, dict)
    assert len(result) == test_case.interval_count
    assert len(adapter.count_sqls) == test_case.expected_query_count
    assert all(sql.count("AS __sqb_count_") <= 100 for sql in adapter.count_sqls)
    assert all("AS __sqb_count_0" in sql for sql in adapter.count_sqls)
    occupied: set[int] = set(test_case.occupied_values)
    assert result == {
        (str(value), str(value + 1)): int(value in occupied)
        for value in range(test_case.interval_count)
    }


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="any_watermarks_when_one_input_is_empty_then_runtime_uses_populated_alternative",
            expected_outcome="2026-07-03T00:00:00",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_any_watermarks_when_one_input_is_empty_then_runtime_uses_populated_alternative(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    connection.execute("CREATE TABLE main.target_events (event_time TIMESTAMP)")
    connection.execute("CREATE TABLE main.empty_events (event_time TIMESTAMP)")
    connection.execute("CREATE TABLE main.live_events (event_time TIMESTAMP)")
    connection.execute("INSERT INTO main.live_events VALUES ('2026-07-01'), ('2026-07-02')")

    bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=adapter,
        connection=connection,
        target_relation="main.target_events",
        target_database=None,
        target_schema="main",
        target_name="target_events",
        spec=RuntimeCursorSpec(
            cursor_column="event_time",
            cursor_type="timestamp",
            cursor_grain="day",
            cursor_start="2026-01-01",
            cursor_input_relations=(
                RuntimeCursorInputRelation(
                    relation="main.empty_events", cursor_column="event_time"
                ),
                RuntimeCursorInputRelation(relation="main.live_events", cursor_column="event_time"),
            ),
            cursor_watermark_mode="any",
        ),
    )

    assert bounds is not None
    assert sentinel_to_token(sentinel=bounds.start) == "2026-07-01T00:00:00"
    assert sentinel_to_token(sentinel=bounds.end) == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="all_watermarks_when_one_input_is_empty_then_runtime_fails_closed",
            expected_outcome="required cursor watermark is empty",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_all_watermarks_when_one_input_is_empty_then_runtime_fails_closed(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    connection.execute("CREATE TABLE main.target_events (event_time TIMESTAMP)")
    connection.execute("CREATE TABLE main.empty_events (event_time TIMESTAMP)")
    connection.execute("CREATE TABLE main.live_events (event_time TIMESTAMP)")
    connection.execute("INSERT INTO main.live_events VALUES ('2026-07-02')")

    with pytest.raises(ExecutorInputError, match=str(test_case.expected_outcome)):
        resolve_runtime_cursor_bounds(
            adapter=adapter,
            connection=connection,
            target_relation="main.target_events",
            target_database=None,
            target_schema="main",
            target_name="target_events",
            spec=RuntimeCursorSpec(
                cursor_column="event_time",
                cursor_type="timestamp",
                cursor_grain="day",
                cursor_start="2026-01-01",
                cursor_input_relations=(
                    RuntimeCursorInputRelation(
                        relation="main.empty_events", cursor_column="event_time"
                    ),
                    RuntimeCursorInputRelation(
                        relation="main.live_events", cursor_column="event_time"
                    ),
                ),
                cursor_watermark_mode="all",
            ),
        )


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="terminal_model_watermark_when_relation_is_empty_then_runtime_uses_declared_domain",
            expected_outcome="2025-12-01T00:00:00",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_terminal_model_watermark_when_relation_is_empty_then_runtime_uses_declared_domain(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    connection.execute("CREATE TABLE main.target_events (event_time TIMESTAMP)")
    connection.execute("CREATE TABLE main.archive_events (event_time TIMESTAMP)")

    bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=adapter,
        connection=connection,
        target_relation="main.target_events",
        target_database=None,
        target_schema="main",
        target_name="target_events",
        spec=RuntimeCursorSpec(
            cursor_column="event_time",
            cursor_type="timestamp",
            cursor_grain="day",
            cursor_start="2025-01-01",
            cursor_input_relations=(
                RuntimeCursorInputRelation(
                    relation="main.archive_events",
                    cursor_column="event_time",
                    terminal_cursor_start="2025-01-01",
                    terminal_cursor_end="2025-12-01",
                ),
            ),
            cursor_watermark_mode="all",
        ),
    )

    assert bounds is not None
    assert sentinel_to_token(sentinel=bounds.start) == "2025-01-01T00:00:00"
    assert sentinel_to_token(sentinel=bounds.end) == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="nonempty_terminal_and_live_watermarks_when_mode_all_then_archive_end_wins",
            expected_outcome="2025-12-01T00:00:00",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_nonempty_terminal_and_live_watermarks_when_mode_all_then_archive_end_wins(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    bounds: CursorBounds | None = resolve_nonempty_terminal_bounds(
        adapter=adapter, connection=connection, mode="all"
    )

    assert bounds is not None
    assert sentinel_to_token(sentinel=bounds.end) == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="nonempty_terminal_and_live_watermarks_when_mode_any_then_live_end_wins",
            expected_outcome="2026-07-03T00:00:00",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_nonempty_terminal_and_live_watermarks_when_mode_any_then_live_end_wins(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    bounds: CursorBounds | None = resolve_nonempty_terminal_bounds(
        adapter=adapter, connection=connection, mode="any"
    )

    assert bounds is not None
    assert sentinel_to_token(sentinel=bounds.end) == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="replay_and_synthetic_facts_when_final_limit_fails_then_state_is_unchanged",
            expected_outcome=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_replay_and_synthetic_facts_when_final_limit_fails_then_state_is_unchanged(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    connection.execute("CREATE TABLE main.orders (id INTEGER)")
    connection.execute("INSERT INTO main.orders VALUES (0), (10), (20)")
    store: _RecordingEventStore = _RecordingEventStore()
    scope: MicrobatchScope = MicrobatchScope(
        scope_kind="direct",
        scope_key="main.orders",
        model_name="orders",
        target_database=None,
        target_schema="main",
        target_name="orders",
        physical_generation_id="generation-1",
    )
    entry: ModelPlanEntry = replace(
        build_integer_reconciliation_plan_entry(),
        resolved_sql="SELECT id FROM main.orders WHERE id >= __SQLBUILD_MICROBATCH_START__ "
        "AND id < __SQLBUILD_MICROBATCH_END__",
        fingerprint_query_sql="SELECT id FROM main.orders",
        microbatch_range=CursorBounds(start="0", end="30"),
        microbatch_limit=2,
        microbatch_limit_action=MicrobatchLimitAction.ERROR,
        fingerprint_version_hash="new-version",
        previous_version_hash="old-version",
        backfill=BackfillResult(action=BackfillAction.FULL),
    )

    progress: list[str] = []
    result: ModelExecutionResult = execute_microbatch_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={},
            seed_locations={},
            source_map={},
            model_audits=(),
            run_id="limited-replay",
            query_change_tracking=False,
            microbatch_event_store=store,
            microbatch_scope=scope,
            microbatch_model_version_hash="new-version",
        ),
        declared_columns=(),
        on_progress=progress.append,
    )

    assert result.error_message is not None
    assert "MICROBATCH LIMIT EXCEEDED" in result.error_message
    assert len(store.writes) == test_case.expected_outcome
    assert not any(message.startswith("runtime plan resolved:") for message in progress)
    assert connection.execute("SELECT COUNT(*) FROM main.orders").fetchone() == (3,)


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="legacy_recovery_outside_model_domain_when_clamping_then_only_overlap_remains",
            expected_outcome=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_legacy_recovery_outside_model_domain_when_clamping_then_only_overlap_remains(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    context: ModelMaterializationContext = ModelMaterializationContext(
        entry=replace(
            build_integer_reconciliation_plan_entry(), cursor_start="10", cursor_end="30"
        ),
        adapter=adapter,
        connection=connection,
        model_locations={},
        seed_locations={},
        source_map={},
        model_audits=(),
        run_id="domain-clamp",
        query_change_tracking=False,
    )

    intervals: tuple[MicrobatchInterval, ...] = _clamp_intervals_to_model_domain(
        context=context,
        intervals=(
            MicrobatchInterval("0", "20"),
            MicrobatchInterval("20", "40"),
            MicrobatchInterval("30", "40"),
        ),
    )

    assert len(intervals) == test_case.expected_outcome
    assert intervals == (
        MicrobatchInterval("10", "20"),
        MicrobatchInterval("20", "30"),
    )


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="full_refresh_wholly_after_cursor_end_when_planning_then_no_batch_is_generated",
            expected_outcome=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_full_refresh_wholly_after_cursor_end_when_planning_then_no_batch_is_generated(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    connection.execute("CREATE TABLE main.orders (id INTEGER)")
    connection.execute("INSERT INTO main.orders VALUES (29)")
    context: ModelMaterializationContext = ModelMaterializationContext(
        entry=replace(
            build_integer_reconciliation_plan_entry(),
            microbatch_strategy="rolling_window",
            cursor_end="30",
            microbatch_range=CursorBounds(start="30", end="30"),
        ),
        adapter=adapter,
        connection=connection,
        model_locations={},
        seed_locations={},
        source_map={},
        model_audits=(),
        run_id="terminal-full-refresh",
        query_change_tracking=False,
    )

    plan: _MicrobatchPlan = _plan_microbatch_windows(
        context=context,
        is_full_refresh=True,
        target_qualified="main.orders",
        warnings=[],
        audit_results=[],
        statement_recorder=StatementRecorder(),
        on_progress=None,
    )

    assert len(plan.batches) == test_case.expected_outcome
    assert plan.resolved_range == CursorBounds(start="30", end="30")
    result: ModelExecutionResult = execute_microbatch_entry(
        context=context, declared_columns=(), is_full_refresh=True
    )
    assert result.batch_count == 0
    assert connection.execute("SELECT id FROM main.orders").fetchall() == [(29,)]


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="no_work_full_refresh_with_absent_destination_when_executing_then_result_is_skipped",
            expected_outcome=ExecutionStatus.SKIPPED,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_no_work_full_refresh_with_absent_destination_when_executing_then_result_is_skipped(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    context: ModelMaterializationContext = ModelMaterializationContext(
        entry=replace(
            build_integer_reconciliation_plan_entry(),
            microbatch_strategy="rolling_window",
            cursor_end="30",
            microbatch_range=CursorBounds(start="30", end="30"),
        ),
        adapter=adapter,
        connection=connection,
        model_locations={},
        seed_locations={},
        source_map={},
        model_audits=(),
        run_id="absent-terminal-full-refresh",
        query_change_tracking=False,
    )

    result: ModelExecutionResult = execute_microbatch_entry(
        context=context, declared_columns=(), is_full_refresh=True
    )

    assert result.status == test_case.expected_outcome
    assert result.promoted_relation is None
    assert result.skip_reason == "no microbatch work and destination relation does not exist"
    assert not adapter.relation_exists(
        connection=connection, database=None, schema="main", name="orders"
    )


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="no_work_first_run_with_absent_destination_when_executing_then_result_is_skipped",
            expected_outcome=ExecutionStatus.SKIPPED,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_no_work_first_run_with_absent_destination_when_executing_then_result_is_skipped(
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    context: ModelMaterializationContext = ModelMaterializationContext(
        entry=replace(
            build_integer_reconciliation_plan_entry(),
            microbatch_range=CursorBounds(start="10", end="10"),
        ),
        adapter=adapter,
        connection=connection,
        model_locations={},
        seed_locations={},
        source_map={},
        model_audits=(),
        run_id="absent-first-run",
        query_change_tracking=False,
    )

    result: ModelExecutionResult = execute_microbatch_entry(context=context, declared_columns=())

    assert result.status == test_case.expected_outcome
    assert result.promoted_relation is None
    assert not adapter.relation_exists(
        connection=connection, database=None, schema="main", name="orders"
    )


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchBehaviorTestCase(
            description="serial_history_with_interior_and_trailing_gaps_when_detecting_then_only_trailing_recovers",
            expected_outcome=MicrobatchInterval("3", "4"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_serial_history_with_interior_and_trailing_gaps_when_detecting_then_only_trailing_recovers(
    test_case: MicrobatchBehaviorTestCase,
) -> None:
    store: _RecordingEventStore = _RecordingEventStore()
    history: _MicrobatchHistoryContext = _MicrobatchHistoryContext(
        store=store,
        scope=SCOPE,
        history=(completion_event(event_id="later", start="2", end="3"),),
        run_type=completion_event(event_id="kind", start="2", end="3").run_type,
        run_start="0",
        run_end="4",
        batch_size="1",
        batch_concurrency=1,
    )

    trailing, interior = _serial_trailing_recovery_only(
        history=history,
        intervals=(MicrobatchInterval("1", "2"), MicrobatchInterval("3", "4")),
        cursor_type="integer",
    )

    assert trailing == (test_case.expected_outcome,)
    assert interior == (MicrobatchInterval("1", "2"),)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
