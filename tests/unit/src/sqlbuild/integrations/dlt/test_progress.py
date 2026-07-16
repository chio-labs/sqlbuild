"""Unit tests for dlt progress collection."""

from __future__ import annotations

import pytest

from sqlbuild.integrations.dlt.classes.sqlbuild_dlt_progress_collector import (
    SqlbuildDltProgressCollector,
)
from tests.unit.src.sqlbuild.integrations.dlt._test_types import DltProgressCollectorTestCase


@pytest.mark.parametrize(
    "test_case",
    (
        DltProgressCollectorTestCase(
            description="summarizes row, file, and job counters",
            updates=(
                ("extract", "raw_orders", 5000, None),
                ("extract", "Resources", 1, 1),
                ("normalize", "Files", 2, 2),
                ("load", "Jobs", 2, 2),
            ),
            expected_fragments=(
                "dlt progress",
                "extract: Resources 1/1, raw_orders 5000",
                "normalize: Files 2/2",
                "load: Jobs 2/2",
            ),
            expected_live_fragments=("dlt extract", "dlt normalize", "dlt load"),
        ),
        DltProgressCollectorTestCase(
            description="keeps labelled counters distinct",
            updates=(
                ("extract", "Resources", 1, 2),
                ("extract", "Resources", 1, 2),
                ("load", "Jobs", 1, 1),
            ),
            expected_fragments=("extract: Resources 2/2", "load: Jobs 1/1"),
            expected_live_fragments=("dlt extract", "dlt load"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dlt_progress_updates_when_collecting_then_summarizes_counters(
    test_case: DltProgressCollectorTestCase,
) -> None:
    live_messages: list[str] = []
    collector: SqlbuildDltProgressCollector = SqlbuildDltProgressCollector(
        on_progress=live_messages.append
    )

    step: str
    name: str
    inc: int
    total: int | None
    for step, name, inc, total in test_case.updates:
        with collector(step):
            collector.update(name, inc=inc, total=total)
    summary: str = collector.format_summary()

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in summary
    expected_live_fragment: str
    for expected_live_fragment in test_case.expected_live_fragments:
        assert any(expected_live_fragment in message for message in live_messages)
