"""Tests for final verbose build phase timing output."""

from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.commands._helpers.build_execution.phase_timings import (
    write_build_phase_timings,
)
from sqlbuild.cli.commands.models import BuildPhaseTimings
from tests.unit.src.sqlbuild.cli.commands._helpers.build_execution._test_types import (
    BuildPhaseTimingsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildPhaseTimingsTestCase(
            description="renders every available monotonic phase duration",
            expected_output=(
                "\nPhase timings\n"
                "  compile                  1.25s\n"
                "  planning                 2.50s\n"
                "  connection preparation   3.75s\n"
                "  schema preparation       0.50s\n"
                "  execution                4.25s\n"
                "  cost collection          1.00s\n"
                "  total                    13.25s\n"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_typed_phase_timings_when_writing_then_renders_available_durations(
    test_case: BuildPhaseTimingsTestCase,
) -> None:
    stream: StringIO = StringIO()

    write_build_phase_timings(
        stream=stream,
        timings=BuildPhaseTimings(
            compile_seconds=1.25,
            planning_seconds=2.5,
            connection_preparation_seconds=3.75,
            schema_preparation_seconds=0.5,
            execution_seconds=4.25,
            cost_collection_seconds=1.0,
            total_seconds=13.25,
        ),
        use_color=False,
    )

    assert stream.getvalue() == test_case.expected_output
