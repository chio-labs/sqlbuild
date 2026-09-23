"""Integration coverage for target retention policies through real CLI builds."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    RetentionDecreasePolicyTestCase,
    TargetMaterializationRetentionTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    LiveRetentionFake,
    install_live_retention_fake,
    run_build,
    write_retention_policy_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RetentionDecreasePolicyTestCase(
            description="decrease is denied by default",
            target_lines=('time_travel_retention = { table = "7d" }',),
            build_flags=("--allow-retention-decrease",),
            expected_exit_code=1,
            expected_fragment="time travel retention decrease is denied for 'orders'",
        ),
        RetentionDecreasePolicyTestCase(
            description="confirmation policy fails non-interactive builds without the flag",
            target_lines=(
                'time_travel_retention = { table = "7d" }',
                'time_travel_retention_decrease = "require_confirmation"',
            ),
            build_flags=(),
            expected_exit_code=1,
            expected_fragment="--allow-retention-decrease",
        ),
        RetentionDecreasePolicyTestCase(
            description="confirmation policy proceeds with the flag",
            target_lines=(
                'time_travel_retention = { table = "7d" }',
                'time_travel_retention_decrease = "require_confirmation"',
            ),
            build_flags=("--allow-retention-decrease",),
            expected_exit_code=0,
            expected_fragment="Completed successfully",
        ),
        RetentionDecreasePolicyTestCase(
            description="allow policy proceeds silently",
            target_lines=(
                'time_travel_retention = { table = "7d" }',
                'time_travel_retention_decrease = "allow"',
            ),
            build_flags=(),
            expected_exit_code=0,
            expected_fragment="Completed successfully",
        ),
        RetentionDecreasePolicyTestCase(
            description="increase is never gated",
            target_lines=('time_travel_retention = { table = "120d" }',),
            build_flags=(),
            expected_exit_code=0,
            expected_fragment="Completed successfully",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_live_retention_when_rebuilding_with_new_target_retention_then_policy_is_enforced(
    test_case: RetentionDecreasePolicyTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install_live_retention_fake(monkeypatch=monkeypatch, fake=LiveRetentionFake(live_days=90))
    write_retention_policy_project(
        project_dir=tmp_path, target_lines=('time_travel_retention = "90d"',)
    )
    first_exit, first_output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)
    assert first_exit == 0, first_output

    write_retention_policy_project(project_dir=tmp_path, target_lines=test_case.target_lines)
    exit_code, output = run_build(project_dir=tmp_path, flags=test_case.build_flags, capsys=capsys)

    assert exit_code == test_case.expected_exit_code, output
    assert test_case.expected_fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        TargetMaterializationRetentionTestCase(
            description="target materialization retention beats project materialization default",
            target_lines=('time_travel_retention = { table = "120d" }',),
            expected_requested_days=frozenset({120}),
        ),
        TargetMaterializationRetentionTestCase(
            description="project materialization default beats target-wide default",
            target_lines=('time_travel_retention = "30d"',),
            expected_requested_days=frozenset({90}),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_materialization_retention_when_building_then_precedence_is_applied(
    test_case: TargetMaterializationRetentionTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake: LiveRetentionFake = LiveRetentionFake(live_days=1)
    install_live_retention_fake(monkeypatch=monkeypatch, fake=fake)
    write_retention_policy_project(project_dir=tmp_path, target_lines=test_case.target_lines)

    exit_code, output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)

    assert exit_code == 0, output
    assert frozenset(fake.requested_days) == test_case.expected_requested_days


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
