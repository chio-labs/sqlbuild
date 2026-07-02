"""Tests for snapshot full-refresh CLI safety enforcement."""

from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.cli.commands.shared.helpers.snapshots.full_refresh import (
    enforce_snapshot_full_refresh_policy,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.spec.models.project import SnapshotsConfig
from tests.unit.src.sqlbuild.cli.commands.shared.helpers._test_types import (
    SnapshotFullRefreshPolicyTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.shared.helpers.helpers import (
    build_snapshot_full_refresh_entry,
)


class _InputStream(StringIO):
    def __init__(self, initial_value: str, *, is_tty: bool) -> None:
        super().__init__(initial_value)
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


POLICY_ERROR_TEST_CASES: list[SnapshotFullRefreshPolicyTestCase] = [
    SnapshotFullRefreshPolicyTestCase(
        description="denies current-state snapshot full refresh by default",
        plan_output=PlanOutput(model_entries=(build_snapshot_full_refresh_entry(),)),
        snapshots_config=SnapshotsConfig(),
        allow_snapshot_full_refresh=False,
        expected_error_fragment="full refresh is denied for snapshot model 'customer_snapshot'",
        expected_help_fragment="snapshot history is recoverable",
    ),
    SnapshotFullRefreshPolicyTestCase(
        description="model deny remains stricter than project allow",
        plan_output=PlanOutput(
            model_entries=(build_snapshot_full_refresh_entry(snapshot_full_refresh="deny"),)
        ),
        snapshots_config=SnapshotsConfig(current_state_full_refresh="allow"),
        allow_snapshot_full_refresh=True,
        expected_error_fragment="full refresh is denied for snapshot model 'customer_snapshot'",
        expected_help_fragment="snapshot history is recoverable",
    ),
    SnapshotFullRefreshPolicyTestCase(
        description="requires confirmation for historical snapshot in non-interactive run",
        plan_output=PlanOutput(
            model_entries=(build_snapshot_full_refresh_entry(observed_at_column="observed_at"),)
        ),
        snapshots_config=SnapshotsConfig(),
        allow_snapshot_full_refresh=False,
        expected_error_fragment="snapshot full refresh requires confirmation",
        expected_help_fragment="--allow-snapshot-full-refresh",
    ),
    SnapshotFullRefreshPolicyTestCase(
        description="rejects incorrect interactive confirmation phrase",
        plan_output=PlanOutput(
            model_entries=(build_snapshot_full_refresh_entry(observed_at_column="observed_at"),)
        ),
        snapshots_config=SnapshotsConfig(),
        allow_snapshot_full_refresh=False,
        expected_error_fragment="snapshot full refresh cancelled",
        input_text="discard everything\n",
        input_is_tty=True,
    ),
]

POLICY_SUCCESS_TEST_CASES: list[SnapshotFullRefreshPolicyTestCase] = [
    SnapshotFullRefreshPolicyTestCase(
        description="allows historical snapshot full refresh with CLI confirmation flag",
        plan_output=PlanOutput(
            model_entries=(build_snapshot_full_refresh_entry(observed_at_column="observed_at"),)
        ),
        snapshots_config=SnapshotsConfig(),
        allow_snapshot_full_refresh=True,
        expected_output="",
    ),
    SnapshotFullRefreshPolicyTestCase(
        description="allows current-state snapshot when project and model policy allow",
        plan_output=PlanOutput(
            model_entries=(build_snapshot_full_refresh_entry(snapshot_full_refresh="allow"),)
        ),
        snapshots_config=SnapshotsConfig(current_state_full_refresh="allow"),
        allow_snapshot_full_refresh=False,
        expected_output="",
    ),
    SnapshotFullRefreshPolicyTestCase(
        description="allows historical snapshot full refresh with exact interactive phrase",
        plan_output=PlanOutput(
            model_entries=(build_snapshot_full_refresh_entry(observed_at_column="observed_at"),)
        ),
        snapshots_config=SnapshotsConfig(),
        allow_snapshot_full_refresh=False,
        expected_output=(
            "Full refresh of snapshot model 'customer_snapshot' may permanently discard "
            "unrecoverable history.\n\n"
            "Type `discard snapshot history for customer_snapshot` to continue: "
        ),
        input_text="discard snapshot history for customer_snapshot\n",
        input_is_tty=True,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    POLICY_ERROR_TEST_CASES,
    ids=[case.description for case in POLICY_ERROR_TEST_CASES],
)
def test_given_unsafe_snapshot_full_refresh_when_enforcing_policy_then_raises_user_error(
    test_case: SnapshotFullRefreshPolicyTestCase,
) -> None:
    with pytest.raises(CliUserError) as exc_info:
        enforce_snapshot_full_refresh_policy(
            plan=test_case.plan_output,
            snapshots_config=test_case.snapshots_config,
            allow_snapshot_full_refresh=test_case.allow_snapshot_full_refresh,
            input_stream=_InputStream(test_case.input_text, is_tty=test_case.input_is_tty),
            output_stream=StringIO(),
        )

    error: CliUserError = exc_info.value
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in error.message
    assert test_case.expected_help_fragment in (error.help or "")


@pytest.mark.parametrize(
    "test_case",
    POLICY_SUCCESS_TEST_CASES,
    ids=[case.description for case in POLICY_SUCCESS_TEST_CASES],
)
def test_given_safe_or_confirmed_snapshot_full_refresh_when_enforcing_policy_then_allows_execution(
    test_case: SnapshotFullRefreshPolicyTestCase,
) -> None:
    output_stream: StringIO = StringIO()

    enforce_snapshot_full_refresh_policy(
        plan=test_case.plan_output,
        snapshots_config=test_case.snapshots_config,
        allow_snapshot_full_refresh=test_case.allow_snapshot_full_refresh,
        input_stream=_InputStream(test_case.input_text, is_tty=test_case.input_is_tty),
        output_stream=output_stream,
    )

    assert output_stream.getvalue() == test_case.expected_output
