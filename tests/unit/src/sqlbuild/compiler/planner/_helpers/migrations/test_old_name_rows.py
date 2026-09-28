"""Unit coverage for the nested old-name block in migration plan text."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.migrations.display import old_name_rows
from sqlbuild.presentation.classes.cli_style import CliStyle
from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations._test_types import (
    OldNameRowsTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations.helpers import old_name_entry


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameRowsTestCase(
            description="planned move with renamed columns and grants",
            action="archive_and_view",
            column_aliases=(("amount", "revenue"),),
            grants_supported=True,
            grants_copied=None,
            reason=None,
            expected_rows=(
                "    old name  prod.revenue",
                "        ├── view  until 2026-10-28",
                "        ├── columns  amount <- revenue",
                "        ├── grants  copied from the old table",
                "        └── old table  archived",
            ),
        ),
        OldNameRowsTestCase(
            description="resumed after the archive without grants support",
            action="view_only",
            column_aliases=(),
            grants_supported=False,
            grants_copied=None,
            reason=None,
            expected_rows=(
                "    old name  prod.revenue",
                "        ├── view  until 2026-10-28",
                "        └── old table  already archived",
            ),
        ),
        OldNameRowsTestCase(
            description="live view reports the grants it copied",
            action="live",
            column_aliases=(),
            grants_supported=True,
            grants_copied=2,
            reason=None,
            expected_rows=(
                "    old name  prod.revenue",
                "        ├── view  live until 2026-10-28",
                "        ├── grants  2 copied from the old table",
                "        └── old table  archived",
            ),
        ),
        OldNameRowsTestCase(
            description="disabled view is left for janitor with its reason",
            action="none",
            column_aliases=(),
            grants_supported=True,
            grants_copied=None,
            reason="name reused by model:revenue",
            expected_rows=(
                "    old name  prod.revenue",
                "        └── left for janitor  name reused by model:revenue",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_old_name_step_when_rendering_then_each_fact_has_its_own_row(
    test_case: OldNameRowsTestCase,
) -> None:
    rows: list[str] = old_name_rows(
        entry=old_name_entry(
            action=test_case.action,
            column_aliases=test_case.column_aliases,
            grants_supported=test_case.grants_supported,
            grants_copied=test_case.grants_copied,
            reason=test_case.reason,
        ),
        style=CliStyle(use_color=False),
    )

    assert tuple(rows) == test_case.expected_rows
