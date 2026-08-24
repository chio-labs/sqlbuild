from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.cli.commands._helpers.cost.output import format_cost_breakdown
from sqlbuild.cost.models import CostRunRecord
from tests.unit.src.sqlbuild.cli.commands._helpers.cost._test_types import (
    CostOutputTestCase,
)
from tests.unit.src.sqlbuild.cost.helpers import build_cost_run_record


@pytest.mark.parametrize(
    "test_case",
    [
        CostOutputTestCase(
            description="wide output aligns full model metrics and all-model total",
            terminal_width=140,
            expected_fragments=(
                "Model",
                "Warehouse",
                "Busy share",
                "Attributed credits",
                "Est. cost",
                "orders",
                "TOTAL",
            ),
        ),
        CostOutputTestCase(
            description="narrow output preserves model credits and estimated cost",
            terminal_width=80,
            expected_fragments=("Model", "Attributed credits", "Est. cost", "orders", "TOTAL"),
            unexpected_fragments=("Warehouse", "Busy share", "Scanned"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_terminal_width_when_formatting_cost_then_expected_columns_are_preserved(
    test_case: CostOutputTestCase,
) -> None:
    record: CostRunRecord = build_cost_run_record(
        run_id="run-output",
        completed_at=datetime(2026, 8, 23, tzinfo=UTC),
    )

    output: str = format_cost_breakdown(
        record=record,
        use_color=False,
        terminal_width=test_case.terminal_width,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output
