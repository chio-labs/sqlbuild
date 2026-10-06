"""Terminal status line of `sqb rename` and `sqb mv` text output."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.refactor.output import render_refactor_text
from sqlbuild.compiler.refactoring.types import RefactorStatus
from tests.unit.src.sqlbuild.cli.commands._helpers.refactor._test_types import (
    RefactorStatusLineTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.refactor.helpers import build_move_plan


@pytest.mark.parametrize(
    "test_case",
    [
        RefactorStatusLineTestCase(
            description="applied one file is singular",
            status=RefactorStatus.APPLIED,
            changed_files=1,
            expected_line="Compiled: ok, 1 file changed",
        ),
        RefactorStatusLineTestCase(
            description="applied several files is plural",
            status=RefactorStatus.APPLIED,
            changed_files=3,
            expected_line="Compiled: ok, 3 files changed",
        ),
        RefactorStatusLineTestCase(
            description="dry run one file is singular",
            status=RefactorStatus.DRY_RUN,
            changed_files=1,
            expected_line="Dry run: compiles, 1 file would change; nothing written",
        ),
        RefactorStatusLineTestCase(
            description="dry run several files is plural",
            status=RefactorStatus.DRY_RUN,
            changed_files=2,
            expected_line="Dry run: compiles, 2 files would change; nothing written",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_changed_file_count_when_rendering_refactor_text_then_status_line_agrees_in_number(
    test_case: RefactorStatusLineTestCase,
) -> None:
    output: str = render_refactor_text(
        plan=build_move_plan(changed_files=test_case.changed_files),
        status=test_case.status,
        diagnostics=(),
        use_color=False,
    )

    assert output.splitlines()[-1] == test_case.expected_line


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
