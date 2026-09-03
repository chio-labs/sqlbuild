"""Test helpers for build executor integration tests."""

from __future__ import annotations

from collections.abc import Callable
from operator import attrgetter
from pathlib import Path
from textwrap import dedent
from typing import Any, cast

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineOptions, CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides, ModelPlanEntry, PlanOutput
from sqlbuild.executor.build.main._execute import execute_build_plan
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    BuildRuntimeParams,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.microbatches.classes.direct_store import (
    DirectMicrobatchEventStore,
    direct_microbatch_scope,
)
from sqlbuild.microbatches.exceptions import MicrobatchStateError
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope, MicrobatchWriteResult
from sqlbuild.microbatches.types import MicrobatchEventStore
from tests.integration.src.sqlbuild.executor.build._test_types import (
    BuildExecutionTestCase,
)


def run_build_for_project(
    *,
    test_case: BuildExecutionTestCase,
    project_dir: Path,
    adapter: DuckDbAdapter,
    connection: Any,
) -> BuildExecutionResult:
    """Discover, compile, plan, then execute a build for a fake project."""

    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered,
        adapter=adapter,
        options=CompilePipelineOptions(no_sql_validation=True),
    )

    plan: PlanOutput = pipeline_result.plan_output

    settings_mode: str | None = discovered.project_config.settings.table_promotion_mode
    promotion_mode: TablePromotionMode = TablePromotionMode(
        settings_mode or adapter.default_table_promotion_mode()
    )
    return execute_build_plan(
        plan=plan,
        adapter=adapter,
        connection_config={"database": str(project_dir / "test.duckdb")},
        connections=(connection,),
        scheduler_connection=connection,
        runtime=BuildRuntimeParams(
            promotion_mode=promotion_mode,
            run_id="test_run",
            query_change_tracking=test_case.query_change_tracking,
            snapshots=discovered.project_config.snapshots,
            allow_snapshot_schema_change=test_case.allow_snapshot_schema_change,
            run_audits=test_case.run_audits,
            run_tests=test_case.run_tests,
            fail_fast=test_case.fail_fast,
        ),
    )


def run_selected_causal_build(
    *,
    project_dir: Path,
    adapter: DuckDbAdapter,
    connection: Any,
    run_id: str,
    select: tuple[str, ...],
    microbatch_state_resolver: Any = None,
    start_cursor_ts: str | None = None,
    end_cursor_ts: str | None = None,
) -> BuildExecutionResult:
    """Compile the full graph while executing only named models against one persisted database."""

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    compiled: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered,
        adapter=adapter,
        options=CompilePipelineOptions(
            no_sql_validation=True,
            connection_config={"database": str(project_dir / "test.duckdb")},
            select=select,
            cursor_overrides=CursorOverrides(start_ts=start_cursor_ts, end_ts=end_cursor_ts),
        ),
    )
    return execute_build_plan(
        plan=compiled.plan_output,
        adapter=adapter,
        connection_config={"database": str(project_dir / "test.duckdb")},
        connections=(connection,),
        scheduler_connection=connection,
        runtime=BuildRuntimeParams(
            promotion_mode=TablePromotionMode(adapter.default_table_promotion_mode()),
            run_id=run_id,
            query_change_tracking=True,
            microbatch_state_resolver=microbatch_state_resolver,
        ),
    )


def causal_model_result(result: BuildExecutionResult, model_name: str) -> ModelExecutionResult:
    """Return one named model result from a causal integration build."""

    results: dict[str, ModelExecutionResult] = {
        model.model_name: model for model in result.model_results
    }
    return results[model_name]


def causal_partition_ranges(
    connection: Any, *, model_name: str, run_id: str
) -> tuple[tuple[str, str], ...]:
    """Read persisted partition-completion ranges for one model run."""

    return tuple(
        connection.execute(
            "SELECT partition_start, partition_end FROM main._sqlbuild_microbatches "
            "WHERE record_type = 'partition_completion' AND model_name = ? "
            "AND execution_run_id = ? ORDER BY partition_start",
            (model_name, run_id),
        ).fetchall()
    )


def causal_delete_statements(result: ModelExecutionResult) -> tuple[str, ...]:
    """Return concrete target-delete statements for a model execution."""

    delete_events: Any = filter(
        lambda event: event.content.startswith("DELETE FROM"), result.lifecycle_events
    )
    return tuple(map(attrgetter("content"), delete_events))


def _monthly_causal_producer_sql(*, id_expression: str) -> str:
    return dedent(
        f"""
        MODEL (
          materialized incremental,
          incremental_strategy delete_insert,
          incremental_mode microbatch,
          cursor event_time,
          cursor_type timestamp,
          cursor_grain month,
          cursor_start '2026-07-01',
          cursor_filter_inputs (raw_events event_time),
          cursor_watermark_inputs (raw_events event_time),
          batch_size 1mo,
          replay_on_change full,
        );
        SELECT {id_expression}, event_time
        FROM __source("raw_events")
        WHERE event_time >= __cursor_start() AND event_time < __cursor_end()
        """
    )


def monthly_causal_producer_sql() -> str:
    """Build the initial monthly producer SQL."""

    return _monthly_causal_producer_sql(id_expression="id")


def replacement_monthly_causal_producer_sql() -> str:
    """Build a semantically equivalent but version-distinct monthly producer."""

    return _monthly_causal_producer_sql(id_expression="CAST(id AS INTEGER) AS id")


def daily_causal_consumer_sql(*, batch_size: str) -> str:
    """Build daily consumer SQL with the requested fixed or effective batch size."""

    return dedent(
        f"""
        MODEL (
          materialized incremental,
          incremental_strategy delete_insert,
          incremental_mode microbatch,
          cursor event_time,
          cursor_type timestamp,
          cursor_grain day,
          cursor_start '2026-07-01',
          cursor_filter_inputs (monthly_events event_time),
          cursor_watermark_inputs (monthly_events event_time),
          batch_size {batch_size},
          lookback 4d,
        );
        SELECT id, event_time
        FROM __ref("monthly_events")
        WHERE event_time >= __cursor_start() AND event_time < __cursor_end()
        """
    )


class FailConsumerTerminalPublication:
    """Direct-store decorator that fails one consumer terminal publication."""

    def __init__(self, *, adapter: DuckDbAdapter, connection: Any) -> None:
        self._adapter = adapter
        self._delegate: MicrobatchEventStore = DirectMicrobatchEventStore(
            adapter=adapter, connection=connection
        )

    def write(self, event: MicrobatchEvent) -> None:
        self._delegate.write(event)

    def write_many(self, events: tuple[MicrobatchEvent, ...]) -> MicrobatchWriteResult:
        writers: dict[bool, Callable[[tuple[MicrobatchEvent, ...]], MicrobatchWriteResult]] = {
            True: self._fail_frontier_write,
            False: self._delegate.write_many,
        }
        return writers[any(event.record_type.value == "consumer_frontier" for event in events)](
            events
        )

    def _fail_frontier_write(self, events: tuple[MicrobatchEvent, ...]) -> MicrobatchWriteResult:
        raise MicrobatchStateError("injected terminal causal publication failure")

    def read_scope_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        return self._delegate.read_scope_history(scope)

    def read_model_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        return self._delegate.read_model_history(scope)

    def resolve(
        self, entry: ModelPlanEntry, current_connection: object
    ) -> tuple[MicrobatchEventStore, MicrobatchScope]:
        """Resolve the failing consumer store and ordinary producer stores."""

        return (
            cast(MicrobatchEventStore, self),
            direct_microbatch_scope(
                adapter=self._adapter, connection=current_connection, entry=entry
            ),
        )


def write_build_project_files(*, project_dir: Path, project_files: dict[str, str]) -> None:
    """Write one build integration project's declared files."""

    for relative_path, contents in project_files.items():
        destination: Path = project_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(contents, encoding="utf-8")


def verify_model_statuses(
    *,
    result: BuildExecutionResult,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert per-model execution statuses match expected."""

    actual_statuses: dict[str, ExecutionStatus] = {
        r.model_name: r.status for r in result.model_results
    }
    expected_name: str
    expected_status: ExecutionStatus
    for expected_name, expected_status in test_case.expected_model_statuses:
        assert actual_statuses.get(expected_name) == expected_status

    actual_errors: dict[str, str] = {
        r.model_name: r.error_message or "" for r in result.model_results
    }
    expected_fragment: str
    for expected_name, expected_fragment in test_case.expected_model_error_fragments:
        assert expected_fragment in actual_errors.get(expected_name, "")

    actual_error_codes: dict[str, str | None] = {
        r.model_name: r.error_code for r in result.model_results
    }
    expected_code: str
    for expected_name, expected_code in test_case.expected_model_error_codes:
        assert actual_error_codes.get(expected_name) == expected_code


def verify_function_statuses(
    *,
    result: BuildExecutionResult,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert per-function execution statuses and error fragments match expected."""

    actual_statuses: dict[str, ExecutionStatus] = {
        r.function_name: r.status for r in result.function_results
    }
    expected_name: str
    expected_status: ExecutionStatus
    for expected_name, expected_status in test_case.expected_function_statuses:
        assert actual_statuses.get(expected_name) == expected_status

    actual_errors: dict[str, str] = {
        r.function_name: r.error_message or "" for r in result.function_results
    }
    expected_fragment: str
    for expected_name, expected_fragment in test_case.expected_function_error_fragments:
        assert expected_fragment in actual_errors.get(expected_name, "")

    actual_error_codes: dict[str, str | None] = {
        r.function_name: r.error_code for r in result.function_results
    }
    expected_code: str
    for expected_name, expected_code in test_case.expected_function_error_codes:
        assert actual_error_codes.get(expected_name) == expected_code


def verify_test_counts(
    *,
    result: BuildExecutionResult,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert test result counts match expected."""

    assert len(result.test_results) == test_case.expected_test_count

    actual_error_codes: dict[str, str | None] = {
        r.test_name: r.error_code for r in result.test_results
    }
    expected_code: str
    for expected_name, expected_code in test_case.expected_test_error_codes:
        assert actual_error_codes.get(expected_name) == expected_code


def verify_audit_counts(
    *,
    result: BuildExecutionResult,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert audit result counts match expected."""

    total_model_audits: int = sum(len(r.audit_results) for r in result.model_results)
    assert total_model_audits == test_case.expected_model_audit_count
    assert len(result.source_audit_results) == test_case.expected_source_audit_count
    assert len(result.end_audit_results) == test_case.expected_end_audit_count
    assert result.warning_count == test_case.expected_warning_count


def verify_warehouse_state(
    *,
    connection: Any,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert actual warehouse state matches expected queries and missing relations."""

    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        cursor: Any = connection.execute(query)
        actual_rows: tuple[tuple[object, ...], ...] = tuple(tuple(row) for row in cursor.fetchall())
        assert actual_rows == expected_rows, (
            f"Query: {query}\nExpected: {expected_rows}\nActual: {actual_rows}"
        )

    relation: str
    for relation in test_case.expected_missing_relations:
        schema: str
        name: str
        schema, _, name = relation.rpartition(".")
        name = name or schema
        schema = schema.removesuffix(name)
        cursor = connection.execute(
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = '{name}'" + f" AND table_schema = '{schema}'" * bool(schema)
        )
        assert cursor.fetchone() is None, f"Relation {relation} should not exist but was found"
