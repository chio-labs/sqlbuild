"""Incomplete lifecycle-event export warning formatting."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.entry.observability import (
    format_event_export_warning,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.entry._test_types import (
    EventExportWarningTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.entry.helpers import build_export_summary


@pytest.mark.parametrize(
    "test_case",
    (
        EventExportWarningTestCase(
            "all delivered",
            (("orders_events", 248, 248, 0, 0),),
            True,
            None,
        ),
        EventExportWarningTestCase(
            "successful command with drops",
            (("orders_events", 248, 108, 0, 140),),
            True,
            "Warning: command completed successfully, but lifecycle event export was "
            "incomplete: 140 of 248 events dropped, 0 failed (sink 'orders_events'). "
            "Increase sinks.lifecycle.shutdown_timeout or check sink health.",
        ),
        EventExportWarningTestCase(
            "failed command with failures",
            (("orders_events", 10, 9, 1, 0),),
            False,
            "Warning: lifecycle event export was incomplete: 0 of 10 events dropped, "
            "1 failed (sink 'orders_events'). "
            "Increase sinks.lifecycle.shutdown_timeout or check sink health.",
        ),
        EventExportWarningTestCase(
            "multiple sinks names only affected sinks",
            (
                ("customer_events", 20, 20, 0, 0),
                ("orders_events", 20, 15, 1, 4),
            ),
            True,
            "Warning: command completed successfully, but lifecycle event export was "
            "incomplete: 4 of 40 event deliveries dropped, 1 failed (sink 'orders_events'). "
            "Increase sinks.lifecycle.shutdown_timeout or check sink health.",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_final_export_summary_when_formatting_warning_then_reports_loss_only(
    test_case: EventExportWarningTestCase,
) -> None:
    message: str | None = format_event_export_warning(
        summary=build_export_summary(test_case.exporter_counts),
        command_succeeded=test_case.command_succeeded,
    )

    assert message == test_case.expected_message


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
