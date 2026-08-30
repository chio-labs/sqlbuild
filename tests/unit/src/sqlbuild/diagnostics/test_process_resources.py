"""Deterministic tests for debug process resource tracking."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from sqlbuild.diagnostics.classes.process_resource_tracker import ProcessResourceTracker
from sqlbuild.diagnostics.models import ProcessResourceUsage
from tests.unit.src.sqlbuild.diagnostics._test_types import ProcessResourceTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        ProcessResourceTestCase(
            description="reports wall CPU deltas and peak RSS from injected samples",
            monotonic_values=(10.0, 13.5),
            resource_values=((1.0, 2.0, None), (2.25, 2.75, 64 * 1024 * 1024)),
            expected_wall_seconds=3.5,
            expected_user_cpu_seconds=1.25,
            expected_system_cpu_seconds=0.75,
            expected_max_rss_bytes=64 * 1024 * 1024,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_process_samples_when_finishing_tracker_then_reports_deterministic_deltas(
    test_case: ProcessResourceTestCase,
) -> None:
    monotonic_values: Iterator[float] = iter(test_case.monotonic_values)
    resource_values: Iterator[tuple[float, float, int | None]] = iter(test_case.resource_values)
    tracker: ProcessResourceTracker = ProcessResourceTracker(
        monotonic=lambda: next(monotonic_values),
        resource_reader=lambda: next(resource_values),
    )

    usage: ProcessResourceUsage = tracker.finish()

    assert usage == ProcessResourceUsage(
        wall_seconds=test_case.expected_wall_seconds,
        user_cpu_seconds=test_case.expected_user_cpu_seconds,
        system_cpu_seconds=test_case.expected_system_cpu_seconds,
        max_rss_bytes=test_case.expected_max_rss_bytes,
    )
