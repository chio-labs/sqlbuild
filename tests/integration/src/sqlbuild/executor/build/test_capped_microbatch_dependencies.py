"""Integration coverage for capped microbatch producer availability."""

from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.spec.contracts.types import MicrobatchLimitAction
from tests.integration.src.sqlbuild.executor.build._test_types import (
    CappedDependencyExecutionTestCase,
)
from tests.integration.src.sqlbuild.executor.build.helpers import (
    capped_dependency_consumer_sql,
    capped_dependency_producer_sql,
    causal_model_result,
    causal_partition_ranges,
    run_selected_causal_build,
    write_build_project_files,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CappedDependencyExecutionTestCase(
            description="cap from start exposes only the materialized prefix",
            limit_action=MicrobatchLimitAction.CAP_FROM_START,
            expected_ids=(1, 2, 3),
            expected_intervals=(
                ("2026-01-01T00:00:00", "2026-01-02T00:00:00"),
                ("2026-01-02T00:00:00", "2026-01-03T00:00:00"),
                ("2026-01-03T00:00:00", "2026-01-04T00:00:00"),
            ),
        ),
        CappedDependencyExecutionTestCase(
            description="cap from end exposes only the materialized suffix",
            limit_action=MicrobatchLimitAction.CAP_FROM_END,
            expected_ids=(3, 4, 5),
            expected_intervals=(
                ("2026-01-03T00:00:00", "2026-01-04T00:00:00"),
                ("2026-01-04T00:00:00", "2026-01-05T00:00:00"),
                ("2026-01-05T00:00:00", "2026-01-06T00:00:00"),
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_capped_upstream_when_building_mixed_graph_then_downstream_uses_only_physical_range(
    tmp_path: Path,
    adapter: DuckDbAdapter,
    causal_connection: Any,
    test_case: CappedDependencyExecutionTestCase,
) -> None:
    write_build_project_files(
        project_dir=tmp_path,
        project_files={
            "sqlbuild_project.toml": 'name = "capped_dependency"\nadapter = "duckdb"\n',
            "sources/raw.yml": (
                "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"
            ),
            "models/capped_events.sql": capped_dependency_producer_sql(
                action=test_case.limit_action
            ),
            "models/downstream_events.sql": capped_dependency_consumer_sql(),
        },
    )
    causal_connection.execute("CREATE TABLE main.raw_events (id INTEGER, event_time TIMESTAMP)")
    causal_connection.execute(
        "INSERT INTO main.raw_events VALUES "
        "(1, '2026-01-01 12:00:00'), (2, '2026-01-02 12:00:00'), "
        "(3, '2026-01-03 12:00:00'), (4, '2026-01-04 12:00:00'), "
        "(5, '2026-01-05 12:00:00')"
    )

    result: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=causal_connection,
        run_id="capped-mixed-graph",
        select=(),
    )

    assert causal_model_result(result, "capped_events").status == ExecutionStatus.SUCCESS
    downstream: ModelExecutionResult = causal_model_result(result, "downstream_events")
    assert downstream.status == ExecutionStatus.SUCCESS
    assert (
        tuple(
            row[0]
            for row in causal_connection.execute(
                "SELECT id FROM main.downstream_events ORDER BY id"
            ).fetchall()
        )
        == test_case.expected_ids
    )
    assert (
        causal_partition_ranges(
            causal_connection,
            model_name="downstream_events",
            run_id="capped-mixed-graph",
        )
        == test_case.expected_intervals
    )


@pytest.mark.parametrize(
    "test_case",
    (
        CappedDependencyExecutionTestCase(
            description="integer cap from end propagates exact interval",
            limit_action=MicrobatchLimitAction.CAP_FROM_END,
            expected_ids=(3, 4),
            expected_intervals=(("70", "91"),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_integer_capped_upstream_when_building_mixed_graph_then_exact_intervals_propagate(
    tmp_path: Path,
    adapter: DuckDbAdapter,
    causal_connection: Any,
    test_case: CappedDependencyExecutionTestCase,
) -> None:
    write_build_project_files(
        project_dir=tmp_path,
        project_files={
            "sqlbuild_project.toml": 'name = "integer_capped_dependency"\nadapter = "duckdb"\n',
            "sources/raw.yml": (
                "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"
            ),
            "models/capped_events.sql": dedent(
                f"""
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  incremental_mode microbatch,
                  microbatch_strategy watermark,
                  cursor batch_id,
                  cursor_type integer,
                  cursor_start 0,
                  cursor_end 101,
                  cursor_watermark_mode all,
                  cursor_inputs (
                    raw_events (column batch_id, roles [filter, watermark]),
                  ),
                  batch_size "25",
                  microbatch_limit (max_batches 2, action {test_case.limit_action.value}),
                );
                SELECT id, batch_id FROM __source("raw_events")
                """
            ),
            "models/downstream_events.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  incremental_mode microbatch,
                  microbatch_strategy watermark,
                  cursor batch_id,
                  cursor_type integer,
                  cursor_start 0,
                  cursor_watermark_mode all,
                  cursor_inputs (
                    capped_events (column batch_id, roles [filter, watermark]),
                  ),
                  batch_size "25",
                );
                SELECT id, batch_id FROM __ref("capped_events")
                """
            ),
        },
    )
    causal_connection.execute("CREATE TABLE main.raw_events (id INTEGER, batch_id INTEGER)")
    causal_connection.execute(
        "INSERT INTO main.raw_events VALUES (1, 10), (2, 30), (3, 70), (4, 90)"
    )

    result: BuildExecutionResult = run_selected_causal_build(
        project_dir=tmp_path,
        adapter=adapter,
        connection=causal_connection,
        run_id="integer-capped-mixed-graph",
        select=(),
    )

    assert causal_model_result(result, "capped_events").status == ExecutionStatus.SUCCESS
    assert causal_model_result(result, "downstream_events").status == ExecutionStatus.SUCCESS
    assert causal_connection.execute(
        "SELECT id FROM main.downstream_events ORDER BY id"
    ).fetchall() == [(value,) for value in test_case.expected_ids]
    assert (
        causal_partition_ranges(
            causal_connection,
            model_name="downstream_events",
            run_id="integer-capped-mixed-graph",
        )
        == test_case.expected_intervals
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
