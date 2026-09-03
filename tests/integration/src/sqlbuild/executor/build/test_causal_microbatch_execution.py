"""Integration coverage proving cross-model completion replay is inert."""

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from tests.integration.src.sqlbuild.executor.build._test_types import CausalExecutionTestCase
from tests.integration.src.sqlbuild.executor.build.helpers import (
    causal_model_result,
    daily_causal_consumer_sql,
    monthly_causal_producer_sql,
    run_selected_causal_build,
    write_build_project_files,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CausalExecutionTestCase(
            description="producer replay remains inert",
            expected_status=ExecutionStatus.SUCCESS,
            expected_minimum_cursor_start="2026-07-27",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_old_producer_replay_when_consumer_runs_normally_then_range_is_not_widened(
    tmp_path: Path,
    adapter: DuckDbAdapter,
    causal_connection: Any,
    test_case: CausalExecutionTestCase,
) -> None:
    connection: Any = causal_connection
    write_build_project_files(
        project_dir=tmp_path,
        project_files={
            "sqlbuild_project.toml": 'name = "completion_inert"\nadapter = "duckdb"\n',
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
        "INSERT INTO main.raw_events VALUES (1, '2026-07-01 12:00:00'), (2, '2026-07-31 12:00:00')"
    )
    initial: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="initial",
        select=(),
    )
    assert causal_model_result(initial, "daily_events").status == ExecutionStatus.SUCCESS
    steady: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="steady",
        select=("daily_events",),
    )
    assert causal_model_result(steady, "daily_events").status == ExecutionStatus.SUCCESS

    producer_replay: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="producer-replay",
        select=("monthly_events",),
        start_cursor_ts="2026-07-01",
        end_cursor_ts="2026-07-01",
    )
    assert causal_model_result(producer_replay, "monthly_events").status == ExecutionStatus.SUCCESS

    ordinary: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
        run_id="ordinary-consumer",
        select=("daily_events",),
    )
    consumer: ModelExecutionResult = causal_model_result(ordinary, "daily_events")
    assert consumer.status == test_case.expected_status
    assert consumer.microbatch_causal_replay_intervals == ()
    assert consumer.microbatch_consumer_frontier_event_ids == ()
    assert consumer.cursor_range_start is not None
    assert consumer.cursor_range_start >= test_case.expected_minimum_cursor_start


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
