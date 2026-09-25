"""Direct event publication remains compatible with older tables' extra columns."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.microbatches.classes.direct_store import DirectMicrobatchEventStore
from sqlbuild.microbatches.main.deterministic_event_id import deterministic_microbatch_event_id
from sqlbuild.microbatches.main.project_coverage import project_microbatch_coverage
from sqlbuild.microbatches.main.project_replay import project_replay_requirement
from sqlbuild.microbatches.models import (
    MicrobatchCoverageProjection,
    MicrobatchEvent,
    MicrobatchInterval,
    ReplayRequirementProjection,
)
from sqlbuild.microbatches.types import MicrobatchRecordType, ReplayRequirementState
from tests.integration.src.sqlbuild.microbatches.classes._test_types import RetiredColumnsTestCase
from tests.integration.src.sqlbuild.microbatches.classes.helpers import build_events

# The previous release's physical schema, intentionally independent of current constants.
OLD_TABLE_DDL: str = """
CREATE TABLE main._sqlbuild_microbatches (
    event_id VARCHAR, record_type VARCHAR, scope_kind VARCHAR, scope_key VARCHAR,
    model_name VARCHAR, target_database VARCHAR, target_schema VARCHAR, target_name VARCHAR,
    physical_generation_id VARCHAR, virtual_environment_name VARCHAR,
    virtual_model_version_hash VARCHAR, origin_run_id VARCHAR, origin_run_started_at TIMESTAMP,
    execution_run_id VARCHAR, execution_run_started_at TIMESTAMP, run_type VARCHAR,
    completion_type VARCHAR, run_start VARCHAR, run_end VARCHAR, partition_start VARCHAR,
    partition_end VARCHAR, batch_size VARCHAR, cursor_column VARCHAR, cursor_type VARCHAR,
    cursor_grain VARCHAR, model_version_hash VARCHAR, definition_hash VARCHAR,
    fingerprint_status VARCHAR, replay_requirement_id VARCHAR, required_model_version_hash VARCHAR,
    previous_model_version_hash VARCHAR, replay_policy VARCHAR, rows_affected BIGINT,
    completed_at TIMESTAMP, coverage_source VARCHAR, observed_row_count BIGINT,
    observed_at TIMESTAMP, synthetic_reason VARCHAR, unaccounted_policy VARCHAR, created_at TIMESTAMP
)
"""


@pytest.mark.parametrize(
    "test_case",
    [
        RetiredColumnsTestCase(
            description="old nullable columns preserve event publication", expected_existing_count=2
        )
    ],
    ids=lambda case: case.description,
)
def test_given_old_table_when_writing_requirements_and_completions_then_projection_succeeds(
    test_case: RetiredColumnsTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        connection.execute(OLD_TABLE_DDL)
        store: DirectMicrobatchEventStore = DirectMicrobatchEventStore(
            adapter=adapter, connection=connection
        )
        completion: MicrobatchEvent = build_events(count=1)[0]
        requirement_id: str = deterministic_microbatch_event_id(
            scope=completion.scope,
            record_type=MicrobatchRecordType.REPLAY_REQUIREMENT,
            partition_start=None,
            partition_end=None,
            completion_reason="F2",
        )
        requirement: MicrobatchEvent = replace(
            completion,
            event_id=requirement_id,
            record_type=MicrobatchRecordType.REPLAY_REQUIREMENT,
            completion_type=None,
            partition_start=None,
            partition_end=None,
            required_model_version_hash="F2",
        )
        store.write(requirement)
        assert tuple(event.event_id for event in store.read_scope_history(completion.scope)) == (
            requirement.event_id,
        )
        store.write(completion)
        assert (
            store.write_many((requirement, completion)).already_existing
            == test_case.expected_existing_count
        )
        history: tuple[MicrobatchEvent, ...] = store.read_scope_history(completion.scope)
        assert {event.event_id for event in history} == {requirement.event_id, completion.event_id}
        intervals: tuple[MicrobatchInterval, ...] = (MicrobatchInterval(start="0", end="1"),)
        coverage: MicrobatchCoverageProjection = project_microbatch_coverage(
            events=history, expected_intervals=intervals, cursor_type="integer"
        )
        projection: ReplayRequirementProjection = project_replay_requirement(
            requirement=requirement,
            current_model_version_hash="F2",
            expected_intervals=intervals,
            coverage=coverage,
            cursor_type="integer",
        )
        assert projection.state == ReplayRequirementState.VERIFIED_COMPLETE
        assert connection.execute(
            "SELECT virtual_environment_name, virtual_model_version_hash "
            "FROM main._sqlbuild_microbatches"
        ).fetchall() == [(None, None), (None, None)]
    finally:
        adapter.close(connection)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
