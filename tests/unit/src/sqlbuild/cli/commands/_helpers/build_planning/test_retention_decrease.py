from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.commands._helpers.build_planning.retention_decrease import (
    enforce_retention_decrease_policy,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.planner.types import RetentionDirection
from tests.unit.src.sqlbuild.cli.commands._helpers.build_planning._test_types import (
    RetentionDecreasePolicyTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.build_planning.helpers import (
    build_retention_entry,
)


class _InputStream(StringIO):
    def __init__(self, initial_value: str, *, is_tty: bool) -> None:
        super().__init__(initial_value)
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


@pytest.mark.parametrize(
    "test_case",
    [
        RetentionDecreasePolicyTestCase(
            description="deny lists affected models even with the CLI flag",
            plan_output=PlanOutput(
                retention_entries=(
                    build_retention_entry(name="orders"),
                    build_retention_entry(name="customers"),
                )
            ),
            allow_retention_decrease=True,
            expected_error_fragment="'orders', 'customers'",
            expected_help_fragment="time_travel_retention_decrease",
        ),
        RetentionDecreasePolicyTestCase(
            description="mixed direction counts as a decrease",
            plan_output=PlanOutput(
                retention_entries=(build_retention_entry(direction=RetentionDirection.MIXED),)
            ),
            allow_retention_decrease=False,
            expected_error_fragment="denied for 'orders'",
            expected_help_fragment="time_travel_retention_decrease",
        ),
        RetentionDecreasePolicyTestCase(
            description="non-interactive confirmation requires CLI flag",
            plan_output=PlanOutput(
                retention_entries=(build_retention_entry(policy="require_confirmation"),)
            ),
            allow_retention_decrease=False,
            expected_error_fragment="requires confirmation",
            expected_help_fragment="--allow-retention-decrease",
        ),
        RetentionDecreasePolicyTestCase(
            description="incorrect interactive phrase cancels",
            plan_output=PlanOutput(
                retention_entries=(build_retention_entry(policy="require_confirmation"),)
            ),
            allow_retention_decrease=False,
            expected_error_fragment="cancelled",
            input_text="decrease everything\n",
            input_is_tty=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_retention_decrease_when_enforcing_then_raises_user_error(
    test_case: RetentionDecreasePolicyTestCase,
) -> None:
    with pytest.raises(CliUserError) as exc_info:
        enforce_retention_decrease_policy(
            plan=test_case.plan_output,
            allow_retention_decrease=test_case.allow_retention_decrease,
            input_stream=_InputStream(test_case.input_text, is_tty=test_case.input_is_tty),
            output_stream=StringIO(),
        )

    error: CliUserError = exc_info.value
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in error.message
    assert test_case.expected_help_fragment in (error.help or "")


@pytest.mark.parametrize(
    "test_case",
    [
        RetentionDecreasePolicyTestCase(
            description="CLI flag confirms required decrease",
            plan_output=PlanOutput(
                retention_entries=(build_retention_entry(policy="require_confirmation"),)
            ),
            allow_retention_decrease=True,
        ),
        RetentionDecreasePolicyTestCase(
            description="allow policy proceeds silently",
            plan_output=PlanOutput(retention_entries=(build_retention_entry(policy="allow"),)),
            allow_retention_decrease=False,
        ),
        RetentionDecreasePolicyTestCase(
            description="increase is never gated",
            plan_output=PlanOutput(
                retention_entries=(build_retention_entry(direction=RetentionDirection.INCREASE),)
            ),
            allow_retention_decrease=False,
        ),
        RetentionDecreasePolicyTestCase(
            description="exact interactive phrase confirms decrease",
            plan_output=PlanOutput(
                retention_entries=(build_retention_entry(policy="require_confirmation"),)
            ),
            allow_retention_decrease=False,
            expected_output=(
                "Decreasing time travel retention for 'orders' permanently discards history "
                "older than the new retention.\n\n"
                "Type `decrease retention for orders` to continue: "
            ),
            input_text="decrease retention for orders\n",
            input_is_tty=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_safe_or_confirmed_retention_change_when_enforcing_then_allows_execution(
    test_case: RetentionDecreasePolicyTestCase,
) -> None:
    output_stream: StringIO = StringIO()

    enforce_retention_decrease_policy(
        plan=test_case.plan_output,
        allow_retention_decrease=test_case.allow_retention_decrease,
        input_stream=_InputStream(test_case.input_text, is_tty=test_case.input_is_tty),
        output_stream=output_stream,
    )

    assert output_stream.getvalue() == test_case.expected_output
