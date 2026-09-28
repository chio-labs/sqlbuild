"""Integration coverage that migration maintenance notices precede the terminal success line."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.column_migrations._test_types import (
    MaintenanceNoticeOrderTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.column_migrations.helpers import (
    CliRun,
    build_with_completed_migrations,
    last_visible_line,
    run_sqb,
)

_MODEL_NOTICE: str = "migrate_from can be removed from 'new_orders'"
_COLUMN_NOTICE: str = "migrate_from can be removed from column 'revenue' of 'fct_orders'"


@pytest.mark.parametrize(
    "test_case",
    [
        MaintenanceNoticeOrderTestCase(
            description="plan reports M101 and M108 before its completion line",
            command=("plan",),
            expected_notices=(_MODEL_NOTICE, _COLUMN_NOTICE),
            expected_final_line="✓ Plan complete  2 selected",
        ),
        MaintenanceNoticeOrderTestCase(
            description="build reports M101 and M108 before its completion line",
            command=("build",),
            expected_notices=(_MODEL_NOTICE, _COLUMN_NOTICE),
            expected_final_line="✓ Completed successfully",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_completed_migrations_when_running_command_then_success_line_is_last(
    test_case: MaintenanceNoticeOrderTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_with_completed_migrations(project_dir=tmp_path, capsys=capsys)

    result: CliRun = run_sqb(project_dir=tmp_path, args=test_case.command, capsys=capsys)

    assert result.exit_code == 0, result.output
    assert tuple(result.stdout.count(notice) for notice in test_case.expected_notices) == (1, 1)
    assert last_visible_line(result.stdout).startswith(test_case.expected_final_line)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
