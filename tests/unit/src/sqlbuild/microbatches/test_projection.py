"""Behavior tests for append-only microbatch interval projection."""

from __future__ import annotations

import pytest

from sqlbuild.microbatches.main.project_coverage import project_microbatch_coverage
from sqlbuild.microbatches.main.project_replay import project_replay_requirement
from sqlbuild.microbatches.models import (
    MicrobatchCoverageProjection,
    MicrobatchInterval,
    ReplayRequirementProjection,
)
from sqlbuild.microbatches.types import MicrobatchFingerprintStatus, ReplayRequirementState
from tests.unit.src.sqlbuild.microbatches._test_types import (
    MicrobatchCoverageProjectionTestCase,
    MicrobatchReplayProjectionTestCase,
)
from tests.unit.src.sqlbuild.microbatches.helpers import (
    completion_event,
    expected_integer_intervals,
    replay_requirement,
    synthetic_completion_event,
    timestamp_completion,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchCoverageProjectionTestCase(
            description="completion islands expose one known gap",
            events=(
                completion_event(event_id="first", start="0", end="1"),
                completion_event(event_id="last", start="2", end="3"),
            ),
            expected_intervals=expected_integer_intervals(),
            cursor_type="integer",
            expected_projected_intervals=(
                ("0", "1", "F2", MicrobatchFingerprintStatus.KNOWN.value),
                ("2", "3", "F2", MicrobatchFingerprintStatus.KNOWN.value),
            ),
            expected_known_missing=(MicrobatchInterval(start="1", end="2"),),
            expected_unaccounted=(),
            expected_contiguous_frontier="1",
        ),
        MicrobatchCoverageProjectionTestCase(
            description="later island leaves prior range unaccounted",
            events=(completion_event(event_id="last", start="2", end="3"),),
            expected_intervals=expected_integer_intervals(),
            cursor_type="integer",
            expected_projected_intervals=(
                ("2", "3", "F2", MicrobatchFingerprintStatus.KNOWN.value),
            ),
            expected_known_missing=(),
            expected_unaccounted=(
                MicrobatchInterval(start="0", end="1"),
                MicrobatchInterval(start="1", end="2"),
            ),
            expected_contiguous_frontier="0",
        ),
        MicrobatchCoverageProjectionTestCase(
            description="ordinary completion supersedes overlapping synthetic coverage",
            events=(
                synthetic_completion_event(event_id="synthetic", start="0", end="2"),
                completion_event(
                    event_id="ordinary",
                    start="1",
                    end="2",
                    created_offset=1,
                ),
            ),
            expected_intervals=expected_integer_intervals()[:2],
            cursor_type="integer",
            expected_projected_intervals=(
                ("0", "1", None, MicrobatchFingerprintStatus.UNKNOWN.value),
                ("1", "2", "F2", MicrobatchFingerprintStatus.KNOWN.value),
            ),
            expected_known_missing=(),
            expected_unaccounted=(),
            expected_contiguous_frontier="2",
        ),
        MicrobatchCoverageProjectionTestCase(
            description="partial known coverage preserves provenance and returns only the gap",
            events=(completion_event(event_id="known", start="0", end="1"),),
            expected_intervals=(MicrobatchInterval(start="0", end="2"),),
            cursor_type="integer",
            expected_projected_intervals=(
                ("0", "1", "F2", MicrobatchFingerprintStatus.KNOWN.value),
            ),
            expected_known_missing=(),
            expected_unaccounted=(MicrobatchInterval(start="1", end="2"),),
            expected_contiguous_frontier="1",
        ),
        MicrobatchCoverageProjectionTestCase(
            description="latest timestamp provenance wins only on its overlap",
            events=(
                timestamp_completion(
                    event_id="wide",
                    start="2026-01-01T00:00:00",
                    end="2026-01-01T04:00:00",
                    version="F1",
                    offset=0,
                ),
                timestamp_completion(
                    event_id="new-middle",
                    start="2026-01-01T01:00:00",
                    end="2026-01-01T03:00:00",
                    version="F2",
                    offset=1,
                ),
            ),
            expected_intervals=tuple(
                MicrobatchInterval(
                    start=f"2026-01-01T0{hour}:00:00",
                    end=f"2026-01-01T0{hour + 1}:00:00",
                )
                for hour in range(4)
            ),
            cursor_type="timestamp",
            expected_projected_intervals=(
                ("2026-01-01T00:00:00", "2026-01-01T01:00:00", "F1", "known"),
                ("2026-01-01T01:00:00", "2026-01-01T02:00:00", "F2", "known"),
                ("2026-01-01T02:00:00", "2026-01-01T03:00:00", "F2", "known"),
                ("2026-01-01T03:00:00", "2026-01-01T04:00:00", "F1", "known"),
            ),
            expected_known_missing=(),
            expected_unaccounted=(),
            expected_contiguous_frontier="2026-01-01T04:00:00",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_completion_history_when_projecting_then_expected_coverage_is_returned(
    test_case: MicrobatchCoverageProjectionTestCase,
) -> None:
    projection: MicrobatchCoverageProjection = project_microbatch_coverage(
        events=test_case.events,
        expected_intervals=test_case.expected_intervals,
        cursor_type=test_case.cursor_type,
    )

    assert (
        tuple(
            (
                interval.start,
                interval.end,
                interval.model_version_hash,
                interval.fingerprint_status.value,
            )
            for interval in projection.intervals
        )
        == test_case.expected_projected_intervals
    )
    assert projection.known_missing == test_case.expected_known_missing
    assert projection.unaccounted == test_case.expected_unaccounted
    assert projection.contiguous_frontier == test_case.expected_contiguous_frontier


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchReplayProjectionTestCase(
            description="mixed replay coverage separates missing and unknown intervals",
            requirement=replay_requirement(),
            current_model_version_hash="F2",
            events=(
                completion_event(event_id="current", start="0", end="1"),
                synthetic_completion_event(event_id="unknown", start="1", end="2"),
                completion_event(event_id="old", start="2", end="3", version="F1"),
            ),
            expected_intervals=expected_integer_intervals(),
            expected_state=ReplayRequirementState.INCOMPLETE,
            expected_missing=(MicrobatchInterval(start="2", end="3"),),
            expected_unknown_fingerprints=(MicrobatchInterval(start="1", end="2"),),
        ),
        MicrobatchReplayProjectionTestCase(
            description="new expected version supersedes old requirement",
            requirement=replay_requirement(required_version="F2"),
            current_model_version_hash="F3",
            events=(),
            expected_intervals=expected_integer_intervals(),
            expected_state=ReplayRequirementState.SUPERSEDED,
            expected_missing=(),
            expected_unknown_fingerprints=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_replay_requirement_when_projecting_then_expected_state_is_returned(
    test_case: MicrobatchReplayProjectionTestCase,
) -> None:
    coverage: MicrobatchCoverageProjection = project_microbatch_coverage(
        events=test_case.events,
        expected_intervals=test_case.expected_intervals,
        cursor_type="integer",
    )
    replay: ReplayRequirementProjection = project_replay_requirement(
        requirement=test_case.requirement,
        current_model_version_hash=test_case.current_model_version_hash,
        expected_intervals=test_case.expected_intervals,
        coverage=coverage,
        cursor_type="integer",
    )

    assert replay.state == test_case.expected_state
    assert replay.missing == test_case.expected_missing
    assert replay.unknown_fingerprints == test_case.expected_unknown_fingerprints


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
