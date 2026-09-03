"""End-to-end scheduler coverage for serial causal microbatch execution."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from tests.integration.src.sqlbuild.executor.build._test_types import (
    BuildExecutionTestCase,
    CausalBuildExecutionTestCase,
)
from tests.integration.src.sqlbuild.executor.build.helpers import (
    FailConsumerTerminalPublication,
    causal_delete_statements,
    causal_model_result,
    causal_partition_ranges,
    daily_causal_consumer_sql,
    monthly_causal_producer_sql,
    replacement_monthly_causal_producer_sql,
    run_build_for_project,
    run_selected_causal_build,
    write_build_project_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CausalBuildExecutionTestCase(
            description="monthly producer causal replay lifecycle", expected_batch_count=31
        )
    ],
    ids=lambda case: case.description,
)
def test_given_monthly_producer_and_daily_consumers_when_replacement_completes_then_only_causal_replay_coarsens_batches(
    test_case: CausalBuildExecutionTestCase,
    tmp_path: Path,
    adapter: DuckDbAdapter,
    causal_connection: Any,
) -> None:
    connection: Any = causal_connection
    write_build_project_files(
        project_dir=tmp_path,
        project_files={
            "sqlbuild_project.toml": 'name = "causal_incident"\nadapter = "duckdb"\n',
            "sources/raw.yml": (
                "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"
            ),
            "models/monthly_events.sql": monthly_causal_producer_sql(),
            "models/daily_fixed.sql": daily_causal_consumer_sql(batch_size="1d"),
            "models/daily_effective.sql": daily_causal_consumer_sql(batch_size="effective"),
        },
    )
    connection.execute("CREATE TABLE main.raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO main.raw_events VALUES (1, '2026-07-01 12:00:00'), (2, '2026-07-31 12:00:00')"
    )

    initial: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="initial",
        select=(),
    )
    steady: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="steady-fixed",
        select=("daily_fixed",),
    )
    steady_fixed: ModelExecutionResult = causal_model_result(steady, "daily_fixed")

    assert initial.status == BuildStatus.SUCCESS
    assert tuple(model.model_name for model in steady.model_results) == ("daily_fixed",)
    assert steady_fixed.status == ExecutionStatus.SUCCESS
    assert steady_fixed.microbatch_causal_history_status == "known"
    assert steady_fixed.microbatch_causal_replay_intervals == ()
    assert steady_fixed.cursor_range_start == "2026-07-27T00:00:00"
    assert steady_fixed.cursor_range_end == "2026-08-01T00:00:00"
    assert steady_fixed.batch_size == "1d"
    assert steady_fixed.batch_count == 5
    steady_deletes: tuple[str, ...] = causal_delete_statements(steady_fixed)
    assert len(steady_deletes) == 5
    assert "2026-07-27T00:00:00" in steady_deletes[0]
    assert "2026-07-28T00:00:00" in steady_deletes[0]
    assert "2026-07-31T00:00:00" in steady_deletes[-1]
    assert "2026-08-01T00:00:00" in steady_deletes[-1]

    write_build_project_files(
        project_dir=tmp_path,
        project_files={"models/monthly_events.sql": replacement_monthly_causal_producer_sql()},
    )
    replacement: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="producer-replacement",
        select=("monthly_events",),
    )
    replacement_producer: ModelExecutionResult = causal_model_result(replacement, "monthly_events")

    assert replacement.status == BuildStatus.SUCCESS
    assert replacement_producer.cursor_range_start == "2026-07-01T00:00:00"
    assert replacement_producer.cursor_range_end == "2026-08-01T00:00:00"
    assert replacement_producer.batch_size == "1mo"
    assert replacement_producer.batch_count == 1

    fixed_replay: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="fixed-replay",
        select=("daily_fixed",),
    )
    fixed_consumer: ModelExecutionResult = causal_model_result(fixed_replay, "daily_fixed")
    fixed_ranges: tuple[tuple[str, str], ...] = causal_partition_ranges(
        connection, model_name="daily_fixed", run_id="fixed-replay"
    )

    assert fixed_replay.status == BuildStatus.SUCCESS
    assert fixed_consumer.microbatch_causal_replay_intervals == (
        ("2026-07-01", "2026-08-01T00:00:00"),
    )
    assert fixed_consumer.cursor_range_start == "2026-07-01T00:00:00"
    assert fixed_consumer.cursor_range_end == "2026-08-01T00:00:00"
    assert fixed_consumer.batch_size == "1d"
    assert fixed_consumer.batch_count == test_case.expected_batch_count
    assert len(fixed_ranges) == test_case.expected_batch_count
    assert fixed_ranges[0] == ("2026-07-01T00:00:00", "2026-07-02T00:00:00")
    assert fixed_ranges[-1] == ("2026-07-31T00:00:00", "2026-08-01T00:00:00")

    effective_replay: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="effective-replay",
        select=("daily_effective",),
    )
    effective_consumer: ModelExecutionResult = causal_model_result(
        effective_replay, "daily_effective"
    )

    assert effective_replay.status == BuildStatus.SUCCESS
    assert effective_consumer.microbatch_causal_replay_intervals == (
        ("2026-07-01", "2026-08-01T00:00:00"),
    )
    assert effective_consumer.cursor_range_start == "2026-07-01T00:00:00"
    assert effective_consumer.cursor_range_end == "2026-08-01T00:00:00"
    assert effective_consumer.batch_size == "1mo"
    assert effective_consumer.batch_count == 1
    assert causal_partition_ranges(
        connection, model_name="daily_effective", run_id="effective-replay"
    ) == (("2026-07-01T00:00:00", "2026-08-01T00:00:00"),)

    acknowledged: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="acknowledged-fixed",
        select=("daily_fixed",),
    )
    acknowledged_fixed: ModelExecutionResult = causal_model_result(acknowledged, "daily_fixed")

    assert acknowledged.status == BuildStatus.SUCCESS
    assert acknowledged_fixed.microbatch_causal_replay_intervals == ()
    assert acknowledged_fixed.cursor_range_start == "2026-07-27T00:00:00"
    assert acknowledged_fixed.cursor_range_end == "2026-08-01T00:00:00"
    assert acknowledged_fixed.batch_size == "1d"
    assert acknowledged_fixed.batch_count == 5
    assert connection.execute(
        "SELECT COUNT(*) FROM main._sqlbuild_microbatches "
        "WHERE record_type = 'consumer_frontier' AND model_name = 'daily_fixed'"
    ).fetchone() == (2,)


@pytest.mark.parametrize(
    "test_case",
    [
        CausalBuildExecutionTestCase(
            description="consumer terminal publication retry", expected_batch_count=31
        )
    ],
    ids=lambda case: case.description,
)
def test_given_outstanding_monthly_completion_when_consumer_terminal_publication_fails_then_retry_converges_without_early_acknowledgement(
    test_case: CausalBuildExecutionTestCase,
    tmp_path: Path,
    adapter: DuckDbAdapter,
    causal_connection: Any,
) -> None:
    connection: Any = causal_connection
    write_build_project_files(
        project_dir=tmp_path,
        project_files={
            "sqlbuild_project.toml": 'name = "causal_retry"\nadapter = "duckdb"\n',
            "sources/raw.yml": (
                "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"
            ),
            "models/monthly_events.sql": monthly_causal_producer_sql(),
            "models/daily_fixed.sql": daily_causal_consumer_sql(batch_size="1d"),
        },
    )
    connection.execute("CREATE TABLE main.raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute("INSERT INTO main.raw_events VALUES (1, '2026-07-31 12:00:00')")
    initial: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="initial",
        select=(),
    )
    write_build_project_files(
        project_dir=tmp_path,
        project_files={"models/monthly_events.sql": replacement_monthly_causal_producer_sql()},
    )
    replacement: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="producer-replacement",
        select=("monthly_events",),
    )
    failing_store: FailConsumerTerminalPublication = FailConsumerTerminalPublication(
        adapter=adapter, connection=connection
    )

    failed: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="consumer-retry",
        select=("daily_fixed",),
        microbatch_state_resolver=failing_store.resolve,
    )
    failed_consumer: ModelExecutionResult = causal_model_result(failed, "daily_fixed")

    assert initial.status == BuildStatus.SUCCESS
    assert replacement.status == BuildStatus.SUCCESS
    assert failed.status == BuildStatus.FAILED
    assert failed_consumer.status == ExecutionStatus.FAILED
    assert "injected terminal causal publication failure" in (failed_consumer.error_message or "")
    assert connection.execute(
        "SELECT COUNT(*) FROM main._sqlbuild_microbatches "
        "WHERE record_type = 'consumer_frontier' AND model_name = 'daily_fixed' "
        "AND execution_run_id = 'consumer-retry'"
    ).fetchone() == (0,)
    failed_partition_ranges: tuple[tuple[str, str], ...] = causal_partition_ranges(
        connection, model_name="daily_fixed", run_id="consumer-retry"
    )
    assert len(failed_partition_ranges) == test_case.expected_batch_count

    retry: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="consumer-retry",
        select=("daily_fixed",),
    )
    retry_consumer: ModelExecutionResult = causal_model_result(retry, "daily_fixed")

    assert retry.status == BuildStatus.SUCCESS
    assert retry_consumer.status == ExecutionStatus.SUCCESS
    assert retry_consumer.microbatch_causal_replay_intervals == (
        ("2026-07-01", "2026-08-01T00:00:00"),
    )
    assert retry_consumer.batch_count == test_case.expected_batch_count
    assert (
        causal_partition_ranges(connection, model_name="daily_fixed", run_id="consumer-retry")
        == failed_partition_ranges
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM main._sqlbuild_microbatches "
        "WHERE record_type = 'consumer_frontier' AND model_name = 'daily_fixed' "
        "AND execution_run_id = 'consumer-retry'"
    ).fetchone() == (1,)
    assert connection.execute(
        "SELECT COUNT(*) FROM main._sqlbuild_microbatches "
        "WHERE record_type = 'producer_completion' AND model_name = 'daily_fixed' "
        "AND execution_run_id = 'consumer-retry'"
    ).fetchone() == (test_case.expected_batch_count,)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="serial producer and consumer publish terminal causal facts",
            project_files={
                "sqlbuild_project.toml": 'name = "causal"\nadapter = "duckdb"\n',
                "sources/raw.yml": (
                    "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"
                ),
                "models/monthly_events.sql": dedent(
                    """
                    MODEL (
                      materialized incremental,
                      incremental_strategy delete_insert,
                      incremental_mode microbatch,
                      cursor event_time,
                      cursor_type timestamp,
                      cursor_grain month,
                      cursor_filter_inputs (raw_events event_time),
                      cursor_watermark_inputs (raw_events event_time),
                      batch_size 1mo,
                    );
                    SELECT id, event_time
                    FROM __source("raw_events")
                    WHERE event_time >= __cursor_start() AND event_time < __cursor_end()
                    """
                ),
                "models/daily_events.sql": dedent(
                    """
                    MODEL (
                      materialized incremental,
                      incremental_strategy delete_insert,
                      incremental_mode microbatch,
                      cursor event_time,
                      cursor_type timestamp,
                      cursor_grain day,
                      cursor_filter_inputs (monthly_events event_time),
                      cursor_watermark_inputs (monthly_events event_time),
                      batch_size effective,
                      lookback 1d,
                    );
                    SELECT id, event_time
                    FROM __ref("monthly_events")
                    WHERE event_time >= __cursor_start() AND event_time < __cursor_end()
                    """
                ),
            },
            setup_sql=(
                "CREATE TABLE main.raw_events (id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO main.raw_events VALUES (1, '2026-07-15 12:00:00')",
            ),
            expected_status=BuildStatus.SUCCESS,
            expected_model_statuses=(
                ("monthly_events", ExecutionStatus.SUCCESS),
                ("daily_events", ExecutionStatus.SUCCESS),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_serial_causal_chain_when_building_then_store_and_frontier_advance_after_success(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_build_project_files(project_dir=tmp_path, project_files=test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert result.status == test_case.expected_status, result.model_results
    results: dict[str, ModelExecutionResult] = {
        model.model_name: model for model in result.model_results
    }
    consumer: ModelExecutionResult = results["daily_events"]
    assert consumer.status == test_case.expected_model_statuses[1][1]
    assert consumer.microbatch_concurrent_enabled is False
    assert consumer.microbatch_causal_history_status == "known"
    assert consumer.batch_size == "1mo"
    assert len(consumer.microbatch_consumer_frontier_event_ids) == 1
    event_counts: dict[str, int] = dict(
        connection.execute(
            "SELECT record_type, COUNT(*) FROM main._sqlbuild_microbatches GROUP BY record_type"
        ).fetchall()
    )
    assert event_counts["producer_completion"] == 4
    assert event_counts["consumer_frontier"] == 1


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionTestCase(
            description="post-hook failure retains applied producer evidence",
            project_files={
                "sqlbuild_project.toml": 'name = "causal_failure"\nadapter = "duckdb"\n',
                "sources/raw.yml": (
                    "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"
                ),
                "models/events.sql": dedent(
                    """
                    MODEL (
                      materialized incremental,
                      incremental_strategy delete_insert,
                      incremental_mode microbatch,
                      cursor event_time,
                      cursor_type timestamp,
                      cursor_grain day,
                      cursor_filter_inputs (raw_events event_time),
                      cursor_watermark_inputs (raw_events event_time),
                      batch_size 1d,
                      post_hooks [inline_sql('SELECT * FROM missing_post_hook_relation')],
                    );
                    SELECT id, event_time
                    FROM __source("raw_events")
                    WHERE event_time >= __cursor_start() AND event_time < __cursor_end()
                    """
                ),
            },
            setup_sql=(
                "CREATE TABLE main.raw_events (id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO main.raw_events VALUES (1, '2026-07-15 12:00:00')",
            ),
            expected_status=BuildStatus.FAILED,
            expected_model_statuses=(("events", ExecutionStatus.FAILED),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_applied_batch_when_post_hook_fails_then_producer_completion_remains_published(
    test_case: BuildExecutionTestCase,
    tmp_path: Path,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_build_project_files(project_dir=tmp_path, project_files=test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=test_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert result.status == test_case.expected_status
    event_counts: dict[str, int] = dict(
        connection.execute(
            "SELECT record_type, COUNT(*) FROM main._sqlbuild_microbatches GROUP BY record_type"
        ).fetchall()
    )
    assert event_counts["partition_completion"] >= 1
    assert event_counts.get("producer_completion", 0) >= 1


@pytest.mark.parametrize(
    "test_case",
    [CausalBuildExecutionTestCase(description="partial producer failure", expected_batch_count=2)],
    ids=lambda case: case.description,
)
def test_given_later_producer_batch_fails_when_prior_batches_applied_then_prior_causal_facts_remain(
    test_case: CausalBuildExecutionTestCase,
    tmp_path: Path,
    adapter: DuckDbAdapter,
    causal_connection: Any,
) -> None:
    connection: Any = causal_connection
    write_build_project_files(
        project_dir=tmp_path,
        project_files={
            "sqlbuild_project.toml": 'name = "partial_producer"\nadapter = "duckdb"\n',
            "sources/raw.yml": (
                "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"
            ),
            "models/events.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  incremental_mode microbatch,
                  cursor event_time,
                  cursor_type timestamp,
                  cursor_grain day,
                  cursor_start '2026-01-01',
                  cursor_filter_inputs (raw_events event_time),
                  cursor_watermark_inputs (raw_events event_time),
                  batch_size 1d,
                );
                SELECT CASE WHEN id < 0 THEN CAST('invalid' AS INTEGER) ELSE id END AS id, event_time
                FROM __source("raw_events")
                WHERE event_time >= __cursor_start() AND event_time < __cursor_end()
                """
            ),
        },
    )
    connection.execute("CREATE TABLE main.raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute("INSERT INTO main.raw_events VALUES (1, '2026-01-01 12:00:00')")
    initial: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="initial",
        select=("events",),
    )
    connection.execute(
        "INSERT INTO main.raw_events VALUES (2, '2026-01-02 12:00:00'), (-1, '2026-01-03 12:00:00')"
    )

    failed: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="partial-failure",
        select=("events",),
    )

    assert initial.status == BuildStatus.SUCCESS
    assert failed.status == BuildStatus.FAILED
    completed: tuple[tuple[str, str], ...] = tuple(
        connection.execute(
            "SELECT partition_start, partition_end FROM main._sqlbuild_microbatches "
            "WHERE record_type = 'producer_completion' AND model_name = 'events' "
            "AND execution_run_id = 'partial-failure' ORDER BY partition_start"
        ).fetchall()
    )
    assert completed == (
        ("2026-01-01T00:00:00", "2026-01-02T00:00:00"),
        ("2026-01-02T00:00:00", "2026-01-03T00:00:00"),
    )
    assert len(completed) == test_case.expected_batch_count


@pytest.mark.parametrize(
    "test_case",
    [CausalBuildExecutionTestCase(description="empty physical batch", expected_batch_count=3)],
    ids=lambda case: case.description,
)
def test_given_sparse_input_when_empty_batch_applies_then_causal_completion_is_published(
    test_case: CausalBuildExecutionTestCase,
    tmp_path: Path,
    adapter: DuckDbAdapter,
    causal_connection: Any,
) -> None:
    connection: Any = causal_connection
    write_build_project_files(
        project_dir=tmp_path,
        project_files={
            "sqlbuild_project.toml": 'name = "sparse_batches"\nadapter = "duckdb"\n',
            "sources/raw.yml": (
                "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"
            ),
            "models/events.sql": daily_causal_consumer_sql(batch_size="1d")
            .replace("monthly_events", "raw_events")
            .replace('__ref("raw_events")', '__source("raw_events")'),
        },
    )
    connection.execute("CREATE TABLE main.raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO main.raw_events VALUES (1, '2026-07-01 12:00:00'), (3, '2026-07-03 12:00:00')"
    )

    result: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="sparse",
        select=("events",),
    )

    model: ModelExecutionResult = causal_model_result(result, "events")
    assert result.status == BuildStatus.SUCCESS
    assert model.batch_count == test_case.expected_batch_count
    assert connection.execute(
        "SELECT COUNT(*) FROM main._sqlbuild_microbatches p "
        "WHERE p.record_type = 'producer_completion' AND p.model_name = 'events' "
        "AND EXISTS (SELECT 1 FROM main._sqlbuild_microbatches c "
        "WHERE c.record_type = 'partition_completion' AND c.model_name = p.model_name "
        "AND c.partition_start = p.partition_start AND c.partition_end = p.partition_end "
        "AND c.rows_affected = 0)"
    ).fetchone() == (1,)


@pytest.mark.parametrize(
    "test_case",
    [CausalBuildExecutionTestCase(description="slow watermark clipping", expected_batch_count=30)],
    ids=lambda case: case.description,
)
def test_given_multi_input_slow_watermark_when_consuming_causal_event_then_remainder_stays_outstanding(
    test_case: CausalBuildExecutionTestCase,
    tmp_path: Path,
    adapter: DuckDbAdapter,
    causal_connection: Any,
) -> None:
    connection: Any = causal_connection
    write_build_project_files(
        project_dir=tmp_path,
        project_files={
            "sqlbuild_project.toml": 'name = "watermark_cap"\nadapter = "duckdb"\n',
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_events\n    schema: main\n    table: raw_events\n"
                "  - name: slow_events\n    schema: main\n    table: slow_events\n"
            ),
            "models/monthly_events.sql": monthly_causal_producer_sql().replace(
                "'2026-07-01'", "'2026-06-01'"
            ),
            "models/daily_events.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  incremental_mode microbatch,
                  cursor event_time,
                  cursor_type timestamp,
                  cursor_grain day,
                  cursor_start '2026-06-01',
                  cursor_filter_inputs (monthly_events event_time),
                  cursor_watermark_inputs (monthly_events event_time, slow_events event_time),
                  batch_size 1d,
                  lookback 4d,
                );
                SELECT p.id, p.event_time
                FROM __ref("monthly_events") AS p CROSS JOIN __source("slow_events") AS s
                WHERE p.event_time >= __cursor_start() AND p.event_time < __cursor_end()
                """
            ),
        },
    )
    connection.execute("CREATE TABLE main.raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute("CREATE TABLE main.slow_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO main.raw_events VALUES (1, '2026-06-30 12:00:00'), (2, '2026-07-31 12:00:00')"
    )
    connection.execute("INSERT INTO main.slow_events VALUES (1, '2026-06-30 12:00:00')")

    initial: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="slow",
        select=(),
    )
    first_consumer: ModelExecutionResult = causal_model_result(initial, "daily_events")
    connection.execute("INSERT INTO main.slow_events VALUES (2, '2026-07-31 12:00:00')")
    resumed: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="caught-up",
        select=("daily_events",),
    )
    resumed_consumer: ModelExecutionResult = causal_model_result(resumed, "daily_events")

    assert initial.status == BuildStatus.SUCCESS
    assert first_consumer.microbatch_causal_replay_intervals == (
        ("2026-06-01", "2026-07-01T00:00:00"),
    )
    assert first_consumer.batch_count == test_case.expected_batch_count
    assert resumed.status == BuildStatus.SUCCESS
    assert resumed_consumer.microbatch_causal_replay_intervals == (
        ("2026-07-01T00:00:00", "2026-08-01T00:00:00"),
    )
    assert resumed_consumer.batch_count == 61


@pytest.mark.parametrize(
    "test_case",
    [CausalBuildExecutionTestCase(description="disjoint causal execution", expected_batch_count=8)],
    ids=lambda case: case.description,
)
def test_given_disjoint_producer_completions_when_consumer_runs_then_intervals_execute_publish_and_acknowledge(
    test_case: CausalBuildExecutionTestCase,
    tmp_path: Path,
    adapter: DuckDbAdapter,
    causal_connection: Any,
) -> None:
    connection: Any = causal_connection
    write_build_project_files(
        project_dir=tmp_path,
        project_files={
            "sqlbuild_project.toml": 'name = "disjoint_causal"\nadapter = "duckdb"\n',
            "sources/raw.yml": (
                "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"
            ),
            "models/monthly_events.sql": monthly_causal_producer_sql()
            .replace("cursor_grain month", "cursor_grain day")
            .replace("batch_size 1mo", "batch_size 1d"),
            "models/daily_events.sql": daily_causal_consumer_sql(batch_size="1d"),
        },
    )
    connection.execute("CREATE TABLE main.raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO main.raw_events VALUES "
        "(1, '2026-07-01 12:00:00'), (2, '2026-07-10 12:00:00'), "
        "(3, '2026-07-11 12:00:00')"
    )
    initial: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="initial",
        select=(),
    )
    first_producer: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="producer-first",
        select=("monthly_events",),
        start_cursor_ts="2026-07-01",
        end_cursor_ts="2026-07-03",
    )
    second_producer: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="producer-second",
        select=("monthly_events",),
        start_cursor_ts="2026-07-10",
        end_cursor_ts="2026-07-12",
    )
    connection.execute("INSERT INTO main.daily_events VALUES (99, '2026-07-11 18:00:00')")

    consumed: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="consumer-disjoint",
        select=("daily_events",),
    )
    consumer: ModelExecutionResult = causal_model_result(consumed, "daily_events")
    partition_ranges: tuple[tuple[str, str], ...] = causal_partition_ranges(
        connection, model_name="daily_events", run_id="consumer-disjoint"
    )

    assert initial.status == BuildStatus.SUCCESS
    assert first_producer.status == BuildStatus.SUCCESS
    assert second_producer.status == BuildStatus.SUCCESS
    assert consumed.status == BuildStatus.SUCCESS
    assert consumer.microbatch_causal_replay_intervals == (
        ("2026-07-01", "2026-07-04T00:00:00"),
        ("2026-07-10T00:00:00", "2026-07-12T00:00:00"),
    )
    assert consumer.batch_count == test_case.expected_batch_count
    assert len(partition_ranges) == test_case.expected_batch_count
    assert ("2026-07-01T00:00:00", "2026-07-02T00:00:00") in partition_ranges
    assert ("2026-07-10T00:00:00", "2026-07-11T00:00:00") in partition_ranges
    assert all(not start.startswith("2026-07-05") for start, _end in partition_ranges)
    assert len(consumer.microbatch_consumer_frontier_event_ids) == 1

    acknowledged: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="consumer-acknowledged",
        select=("daily_events",),
    )
    acknowledged_consumer: ModelExecutionResult = causal_model_result(acknowledged, "daily_events")

    assert acknowledged.status == BuildStatus.SUCCESS
    assert acknowledged_consumer.microbatch_causal_replay_intervals == ()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
