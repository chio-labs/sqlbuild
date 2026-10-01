from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.commands._helpers.build_planning.plan_policies import (
    dbt_interop_plan_safety_gates,
    enforce_plan_safety_policies,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.spec.contracts.models import ExecutionLimitsConfig, SnapshotsConfig
from tests.unit.src.sqlbuild.cli.commands._helpers.build_planning._test_types import (
    DbtPlanSafetyPolicyTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.build_planning.helpers import (
    build_retention_entry,
    build_snapshot_full_refresh_entry,
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
        DbtPlanSafetyPolicyTestCase(
            description="unconfirmed table-type downgrade names the sqb build flag",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(),)),
            expected_error_fragment="table-type downgrade requires confirmation",
            expected_help_fragment="sqb build --allow-table-type-downgrade",
        ),
        DbtPlanSafetyPolicyTestCase(
            description="denied table-type downgrade is refused even on a terminal",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(policy="deny"),)),
            expected_error_fragment="table-type downgrade is denied for 'orders'",
            input_is_tty=True,
        ),
        DbtPlanSafetyPolicyTestCase(
            description="wrong typed table-type confirmation cancels",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(),)),
            expected_error_fragment="table-type downgrade cancelled",
            input_text="yes\n",
            input_is_tty=True,
        ),
        DbtPlanSafetyPolicyTestCase(
            description="unconfirmed retention decrease names the sqb build flag",
            plan_output=PlanOutput(
                retention_entries=(build_retention_entry(policy="require_confirmation"),)
            ),
            expected_error_fragment="time travel retention decrease requires confirmation",
            expected_help_fragment="sqb build --allow-retention-decrease",
        ),
        DbtPlanSafetyPolicyTestCase(
            description="unconfirmed historical snapshot full refresh names the sqb build flag",
            plan_output=PlanOutput(
                model_entries=(build_snapshot_full_refresh_entry(observed_at_column="seen_at"),)
            ),
            expected_error_fragment="snapshot full refresh requires confirmation",
            expected_help_fragment="sqb build --allow-snapshot-full-refresh",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_plan_when_enforcing_dbt_interop_gates_then_refuses_with_dbt_guidance(
    test_case: DbtPlanSafetyPolicyTestCase,
) -> None:
    with pytest.raises(CliUserError) as raised:
        enforce_plan_safety_policies(
            plan=test_case.plan_output,
            gates=dbt_interop_plan_safety_gates(),
            snapshots_config=SnapshotsConfig(),
            target_name="prod",
            execution_limits=ExecutionLimitsConfig(),
            streams=(_InputStream(test_case.input_text, is_tty=test_case.input_is_tty), StringIO()),
        )

    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in raised.value.message
    assert test_case.expected_help_fragment in (raised.value.help or "")
    assert "Pass --allow-" not in (raised.value.help or "")


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPlanSafetyPolicyTestCase(
            description="typed confirmation on a terminal allows the downgrade",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(),)),
            expected_output="Type `downgrade table type for orders` to continue: ",
            input_text="downgrade table type for orders\n",
            input_is_tty=True,
        ),
        DbtPlanSafetyPolicyTestCase(
            description="allow policy proceeds without a prompt",
            plan_output=PlanOutput(table_type_entries=(build_table_type_entry(policy="allow"),)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_confirmed_or_allowed_plan_when_enforcing_dbt_interop_gates_then_proceeds(
    test_case: DbtPlanSafetyPolicyTestCase,
) -> None:
    output_stream: StringIO = StringIO()

    enforce_plan_safety_policies(
        plan=test_case.plan_output,
        gates=dbt_interop_plan_safety_gates(),
        snapshots_config=SnapshotsConfig(),
        target_name="prod",
        execution_limits=ExecutionLimitsConfig(),
        streams=(_InputStream(test_case.input_text, is_tty=test_case.input_is_tty), output_stream),
    )

    assert test_case.expected_output in output_stream.getvalue()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
