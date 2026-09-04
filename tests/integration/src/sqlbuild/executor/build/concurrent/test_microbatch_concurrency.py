"""Scheduler integration coverage for concurrent microbatch sub-work."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from tests.integration.src.sqlbuild.executor.build.concurrent._test_types import (
    ConcurrentBuildTestCase,
    MicrobatchSchedulerTestCase,
)
from tests.integration.src.sqlbuild.executor.build.concurrent.helpers import (
    run_concurrent_build,
)


class _TrackingDuckDbAdapter(DuckDbAdapter):
    def __init__(self) -> None:
        self.track_delta_staging = False
        self.active_delta_staging = 0
        self.max_active_delta_staging = 0
        self.active_delta_models: dict[str, int] = {}
        self.max_active_delta_models = 0
        self.unattributed_delta_staging = 0
        self._tracking_lock = threading.Lock()

    def _execute(self, *, connection: Any, sql: str) -> Any:
        tracked: bool = (
            self.track_delta_staging and "CREATE OR REPLACE TABLE" in sql and "__delta_" in sql
        )
        model_name: str = sql.split("__delta_", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]
        if tracked:
            with self._tracking_lock:
                if CostContext.current() is None:
                    self.unattributed_delta_staging += 1
                self.active_delta_staging += 1
                self.active_delta_models[model_name] = (
                    self.active_delta_models.get(model_name, 0) + 1
                )
                self.max_active_delta_staging = max(
                    self.max_active_delta_staging, self.active_delta_staging
                )
                self.max_active_delta_models = max(
                    self.max_active_delta_models,
                    len(self.active_delta_models),
                )
            time.sleep(0.05)
        try:
            return super()._execute(connection=connection, sql=sql)
        finally:
            if tracked:
                with self._tracking_lock:
                    self.active_delta_staging -= 1
                    remaining: int = self.active_delta_models[model_name] - 1
                    if remaining:
                        self.active_delta_models[model_name] = remaining
                    else:
                        del self.active_delta_models[model_name]


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchSchedulerTestCase(
            description="two microbatch models share three global workers",
            expected_status=BuildStatus.SUCCESS,
            expected_max_active_batches=3,
            expected_max_active_models=2,
            expected_row_count=6,
            expected_completion_count=14,
            expected_unattributed_batches=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_three_batch_ceiling_when_incremental_runs_then_batches_overlap(
    test_case: MicrobatchSchedulerTestCase, tmp_path: Path
) -> None:
    project_files: dict[str, str] = {
        "sqlbuild_project.toml": dedent(
            """
            name = "concurrent_microbatch_project"
            adapter = "duckdb"

            [connection]
            database = "test.duckdb"

            [settings]
            concurrency = 3
            microbatch_concurrency = true
            """
        ).strip()
        + "\n",
        "sources/raw.yml": dedent(
            """
            sources:
              - name: raw_events
                schema: main
                table: raw_events
            """
        ).strip()
        + "\n",
        "models/orders.sql": dedent(
            """
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
          microbatch_strategy watermark,
          cursor_watermark_mode all,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain hour,
              cursor_inputs (
            raw_events (column event_time, roles [filter, watermark]),
          ),
              batch_size 1h,
              batch_concurrency 3,
            );

            SELECT id, event_time, payload
            FROM __source("raw_events")
            WHERE event_time >= __cursor_start()
              AND event_time < __cursor_end()
            """
        ).strip()
        + "\n",
        "models/shipments.sql": dedent(
            """
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
          microbatch_strategy watermark,
          cursor_watermark_mode all,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain hour,
              cursor_inputs (
            raw_events (column event_time, roles [filter, watermark]),
          ),
              batch_size 1h,
              batch_concurrency 3,
            );

            SELECT id, event_time, payload
            FROM __source("raw_events")
            WHERE event_time >= __cursor_start()
              AND event_time < __cursor_end()
            """
        ).strip()
        + "\n",
    }
    write_files: tuple[tuple[str, str], ...] = tuple(project_files.items())
    for relative_path, contents in write_files:
        destination: Path = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(contents, encoding="utf-8")

    adapter: _TrackingDuckDbAdapter = _TrackingDuckDbAdapter()
    db_path: Path = tmp_path / "test.duckdb"
    initial_case: ConcurrentBuildTestCase = ConcurrentBuildTestCase(
        description="initial serial generation",
        project_files=project_files,
        max_concurrency=3,
        expected_status=BuildStatus.SUCCESS,
        setup_sql=(
            "CREATE TABLE raw_events (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "INSERT INTO raw_events VALUES "
            "(1, '2026-01-01 00:30:00', 'a'), "
            "(2, '2026-01-01 01:30:00', 'b'), "
            "(3, '2026-01-01 02:30:00', 'c')",
        ),
    )
    initial_result: BuildExecutionResult = run_concurrent_build(
        test_case=initial_case,
        project_dir=tmp_path,
        db_path=db_path,
        adapter=adapter,
    )
    assert initial_result.status == BuildStatus.SUCCESS

    adapter.track_delta_staging = True
    incremental_case: ConcurrentBuildTestCase = ConcurrentBuildTestCase(
        description="concurrent incremental generation",
        project_files=project_files,
        max_concurrency=3,
        expected_status=BuildStatus.SUCCESS,
        setup_sql=(
            "INSERT INTO raw_events VALUES "
            "(4, '2026-01-01 03:30:00', 'd'), "
            "(5, '2026-01-01 04:30:00', 'e'), "
            "(6, '2026-01-01 05:30:00', 'f')",
        ),
    )
    incremental_result: BuildExecutionResult = run_concurrent_build(
        test_case=incremental_case,
        project_dir=tmp_path,
        db_path=db_path,
        adapter=adapter,
    )

    assert incremental_result.status == test_case.expected_status
    assert adapter.max_active_delta_staging == test_case.expected_max_active_batches
    assert adapter.max_active_delta_models == test_case.expected_max_active_models
    assert adapter.unattributed_delta_staging == test_case.expected_unattributed_batches
    connection: Any = adapter.connect({"database": str(db_path)})
    try:
        assert (
            connection.execute("SELECT COUNT(*) FROM main.orders").fetchone()[0]
            == test_case.expected_row_count
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM main.shipments").fetchone()[0]
            == test_case.expected_row_count
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM main._sqlbuild_microbatches "
                "WHERE record_type = 'partition_completion'"
            ).fetchone()[0]
            == test_case.expected_completion_count
        )
    finally:
        adapter.close(connection)
