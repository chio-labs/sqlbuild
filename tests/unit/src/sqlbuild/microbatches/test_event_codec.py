"""Compatibility coverage for persisted microbatch event decoding."""

from dataclasses import replace

import pytest

from sqlbuild.microbatches.classes.event_codec import MicrobatchEventCodec
from sqlbuild.microbatches.main.project_coverage import project_microbatch_coverage
from sqlbuild.microbatches.models import (
    MicrobatchCoverageProjection,
    MicrobatchEvent,
    MicrobatchInterval,
)
from tests.unit.src.sqlbuild.microbatches._test_types import (
    MicrobatchEventCursorEncodingTestCase,
    RetiredRecordDecodingTestCase,
    UnknownRecordDecodingTestCase,
)
from tests.unit.src.sqlbuild.microbatches.helpers import (
    completion_event,
    event_row_with_record_type,
)


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchEventCursorEncodingTestCase(
            description="offset timestamp cursor fields remain state-table strings",
            run_start="2026-01-01T00:00:00+00:00",
            run_end="2026-01-02T00:00:00+00:00",
            partition_start="2026-01-01T00:00:00+00:00",
            partition_end="2026-01-01T01:00:00+00:00",
            expected_values=(
                "2026-01-01T00:00:00+00:00",
                "2026-01-02T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T01:00:00+00:00",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_cursor_event_when_encoding_then_preserves_state_table_string_formats(
    test_case: MicrobatchEventCursorEncodingTestCase,
) -> None:
    event: MicrobatchEvent = completion_event(
        event_id="timestamp-event",
        start=test_case.partition_start,
        end=test_case.partition_end,
    )
    event = replace(
        event,
        run_start=test_case.run_start,
        run_end=test_case.run_end,
        cursor_type="timestamp",
        cursor_grain="hour",
    )

    values: tuple[object | None, ...] = MicrobatchEventCodec.values(event)

    assert values[17:21] == test_case.expected_values


@pytest.mark.parametrize(
    "test_case",
    (
        RetiredRecordDecodingTestCase(
            description="retired producer completion",
            retired_record_type="producer_completion",
            expected_event_ids=("valid",),
            expected_projected_event_ids=("valid",),
        ),
        RetiredRecordDecodingTestCase(
            description="retired consumer frontier",
            retired_record_type="consumer_frontier",
            expected_event_ids=("valid",),
            expected_projected_event_ids=("valid",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_retired_and_active_rows_when_decoding_then_retired_rows_are_ignored(
    test_case: RetiredRecordDecodingTestCase,
) -> None:
    active: MicrobatchEvent = completion_event(event_id="valid", start="0", end="1")
    retired_row: tuple[object | None, ...] = event_row_with_record_type(
        event=completion_event(event_id="retired", start="1", end="2"),
        record_type=test_case.retired_record_type,
    )

    decoded: tuple[MicrobatchEvent, ...] = MicrobatchEventCodec.from_rows(
        (retired_row, MicrobatchEventCodec.values(active))
    )
    projection: MicrobatchCoverageProjection = project_microbatch_coverage(
        events=decoded,
        expected_intervals=(MicrobatchInterval(start="0", end="1"),),
        cursor_type="integer",
    )

    assert tuple(event.event_id for event in decoded) == test_case.expected_event_ids
    assert (
        tuple(interval.event_id for interval in projection.intervals)
        == test_case.expected_projected_event_ids
    )


@pytest.mark.parametrize(
    "test_case",
    (
        UnknownRecordDecodingTestCase(
            description="unknown record type",
            unknown_record_type="unexpected_completion",
            expected_error_fragment="unexpected_completion",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unknown_row_when_decoding_then_unknown_type_fails_loudly(
    test_case: UnknownRecordDecodingTestCase,
) -> None:
    unknown_row: tuple[object | None, ...] = event_row_with_record_type(
        event=completion_event(event_id="unknown", start="0", end="1"),
        record_type=test_case.unknown_record_type,
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        MicrobatchEventCodec.from_rows((unknown_row,))


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
