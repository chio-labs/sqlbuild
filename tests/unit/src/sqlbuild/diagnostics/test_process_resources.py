"""Deterministic tests for debug process resource tracking."""

from __future__ import annotations

import resource
from collections.abc import Iterator
from unittest.mock import Mock

import pytest

from sqlbuild.diagnostics._helpers.process_resources import read_process_resources
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


@pytest.mark.parametrize(
    "test_case",
    [
        ProcessResourceTestCase(
            description="unsupported maximum RSS sampling retains CPU samples",
            monotonic_values=(0.0, 0.0),
            resource_values=(),
            expected_wall_seconds=0.0,
            expected_user_cpu_seconds=0.0,
            expected_system_cpu_seconds=0.0,
            expected_max_rss_bytes=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_rss_when_sampling_then_cpu_values_are_still_returned(
    test_case: ProcessResourceTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resource, "getrusage", Mock(side_effect=OSError("unsupported")))

    user_cpu, system_cpu, max_rss_bytes = read_process_resources()

    assert user_cpu >= test_case.expected_user_cpu_seconds
    assert system_cpu >= test_case.expected_system_cpu_seconds
    assert max_rss_bytes is test_case.expected_max_rss_bytes
