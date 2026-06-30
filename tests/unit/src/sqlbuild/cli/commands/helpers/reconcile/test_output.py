from __future__ import annotations

import pytest

from sqlbuild.cli.commands.helpers.reconcile.output import format_reconcile_output
from tests.unit.src.sqlbuild.cli.commands.helpers.reconcile._test_types import (
    ReconcileOutputTestCase,
)

TEST_CASES: list[ReconcileOutputTestCase] = [
    ReconcileOutputTestCase(
        description="formats clean reconcile report",
        message="Reconcile report for dev: no issues.",
        expected_text=("\nVirtual reconcile\n\nReconcile report for dev: no issues.\n"),
        expected_color_fragments=(
            "\033[32m\033[1mVirtual reconcile\033[0m",
            "\033[34m\033[1mReconcile report for dev: no issues.\033[0m",
        ),
    ),
    ReconcileOutputTestCase(
        description="formats repair result rows",
        message=(
            "Repair\n"
            "model   fact_orders\n"
            "VDE     dev\n"
            "action  recreate logical view from state\n"
            "result  repaired"
        ),
        expected_text=(
            "\n"
            "Virtual reconcile\n"
            "\n"
            "Repair\n"
            "model   fact_orders\n"
            "VDE     dev\n"
            "action  recreate logical view from state\n"
            "result  repaired\n"
        ),
        expected_color_fragments=(
            "\033[32mRepair\033[0m",
            "  \033[2mmodel   \033[0m \033[34m\033[1mfact_orders\033[0m",
            "  \033[2mVDE     \033[0m \033[34m\033[1mdev\033[0m",
            "  \033[2mresult  \033[0m \033[32mrepaired\033[0m",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_reconcile_message_when_formatting_then_returns_expected_output(
    test_case: ReconcileOutputTestCase,
) -> None:
    text: str = format_reconcile_output(message=test_case.message, use_color=False)
    color_text: str = format_reconcile_output(message=test_case.message, use_color=True)

    assert text == test_case.expected_text
    expected_fragment: str
    for expected_fragment in test_case.expected_color_fragments:
        assert expected_fragment in color_text
