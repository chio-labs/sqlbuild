from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild._native import CliUserError, enforce_plan_safety_policies
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.spec.contracts.models import ExecutionLimitsConfig, SnapshotsConfig
from tests.unit.src.sqlbuild.cli.commands._helpers.build_planning._test_types import (
    TableTypeDowngradePolicyTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.build_planning.helpers import (
    build_policy_gates,
    build_table_type_entry,
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
        TableTypeDowngradePolicyTestCase(
            description="deny lists affected models",
            plan_output=PlanOutput(
                table_type_entries=(
                    build_table_type_entry(name="orders", policy="deny"),
                    build_table_type_entry(name="customers", policy="deny"),
                )
            ),
            allow_table_type_downgrade=False,
            expected_error_fragment="'orders', 'customers'",
        ),
        TableTypeDowngradePolicyTestCase(
            description="non-interactive confirmation requires CLI flag",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(),)),
            allow_table_type_downgrade=False,
            expected_error_fragment="requires confirmation",
            expected_help_fragment="--allow-table-type-downgrade",
        ),
        TableTypeDowngradePolicyTestCase(
            description="incorrect interactive phrase cancels",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(),)),
            allow_table_type_downgrade=False,
            expected_error_fragment="cancelled",
            input_text="downgrade everything\n",
            input_is_tty=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_table_type_downgrade_when_enforcing_then_raises_user_error(
    test_case: TableTypeDowngradePolicyTestCase,
) -> None:
    with pytest.raises(CliUserError) as exc_info:
        enforce_plan_safety_policies(
            plan=test_case.plan_output,
            gates=build_policy_gates(
                allow_table_type_downgrade=test_case.allow_table_type_downgrade
            ),
            snapshots_config=SnapshotsConfig(),
            target_name="dev",
            execution_limits=ExecutionLimitsConfig(),
            streams=(
                _InputStream(test_case.input_text, is_tty=test_case.input_is_tty),
                StringIO(),
            ),
        )

    error: CliUserError = exc_info.value
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in error.message
    assert test_case.expected_help_fragment in (error.help or "")


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeDowngradePolicyTestCase(
            description="CLI flag confirms required downgrade",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(),)),
            allow_table_type_downgrade=True,
        ),
        TableTypeDowngradePolicyTestCase(
            description="allow policy proceeds silently",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(policy="allow"),)),
            allow_table_type_downgrade=False,
        ),
        TableTypeDowngradePolicyTestCase(
            description="upgrade is never gated",
            plan_output=PlanOutput(
                table_type_entries=(
                    build_table_type_entry(
                        downgrade=False,
                        desired_type="permanent",
                        actual_type="transient",
                    ),
                )
            ),
            allow_table_type_downgrade=False,
        ),
        TableTypeDowngradePolicyTestCase(
            description="exact interactive phrase confirms downgrade",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(),)),
            allow_table_type_downgrade=False,
            expected_output=(
                "Downgrading 'orders' to transient may discard up to 90 days of "
                "time-travel history.\n\n"
                "Type `downgrade table type for orders` to continue: "
            ),
            input_text="downgrade table type for orders\n",
            input_is_tty=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_safe_or_confirmed_table_type_change_when_enforcing_then_allows_execution(
    test_case: TableTypeDowngradePolicyTestCase,
) -> None:
    output: StringIO = StringIO()

    enforce_plan_safety_policies(
        plan=test_case.plan_output,
        gates=build_policy_gates(allow_table_type_downgrade=test_case.allow_table_type_downgrade),
        snapshots_config=SnapshotsConfig(),
        target_name="dev",
        execution_limits=ExecutionLimitsConfig(),
        streams=(
            _InputStream(test_case.input_text, is_tty=test_case.input_is_tty),
            output,
        ),
    )

    assert output.getvalue() == test_case.expected_output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
