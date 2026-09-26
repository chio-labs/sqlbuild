"""Migration plan text colour roles and plain rendering."""

from __future__ import annotations

import pytest

from sqlbuild.cli.output.main.plan import format_plan
from sqlbuild.compiler.migrations.types import MigrationCompatibility, MigrationDecision
from sqlbuild.compiler.planner.models import PlanOutput
from tests.unit.src.sqlbuild.compiler.planner.main.pre_build._test_types import (
    MigrationDecisionStyleTestCase,
    MigrationPlainTextTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.main.pre_build.helpers import (
    migration_entry,
    styled_migration_text,
)

_BOLD_BLUE: str = "\033[34m\033[1m"
_BOLD_YELLOW: str = "\033[33m\033[1m"
_BOLD_RED: str = "\033[38;5;167m\033[1m"
_DIM: str = "\033[2m"
_GREEN: str = "\033[32m"
_RED: str = "\033[38;5;167m"
_RESET: str = "\033[0m"


@pytest.mark.parametrize(
    "test_case",
    (
        MigrationDecisionStyleTestCase(
            description="migrate is bold blue with a dim origin arrow and green compatibility",
            decision=MigrationDecision.MIGRATE,
            compatibility=MigrationCompatibility.COMPATIBLE,
            findings=(),
            expected_fragments=(
                f"\033[1mMigrations{_RESET} {_DIM}(1){_RESET}",
                f"  daily_revenue  {_BOLD_BLUE}migrate{_RESET}  "
                f"{_DIM}prod.revenue ->{_RESET} prod.daily_revenue",
                f"    {_DIM}compatibility{_RESET}  {_GREEN}compatible{_RESET}",
                f"    {_DIM}transfer{_RESET}  physical copy, promote by transactional rename",
                f"    {_DIM}discovery{_RESET}  automatic",
            ),
        ),
        MigrationDecisionStyleTestCase(
            description="redo is bold blue",
            decision=MigrationDecision.REDO,
            compatibility=MigrationCompatibility.COMPATIBLE,
            findings=(),
            expected_fragments=(f"{_BOLD_BLUE}redo{_RESET}",),
        ),
        MigrationDecisionStyleTestCase(
            description="done is dim",
            decision=MigrationDecision.DONE,
            compatibility=MigrationCompatibility.NOT_CHECKED,
            findings=(),
            expected_fragments=(f"{_DIM}done{_RESET}",),
        ),
        MigrationDecisionStyleTestCase(
            description="superseded replace is bold yellow",
            decision=MigrationDecision.SUPERSEDED_REPLACE,
            compatibility=MigrationCompatibility.COMPATIBLE,
            findings=(),
            expected_fragments=(f"{_BOLD_YELLOW}superseded replace{_RESET}",),
        ),
        MigrationDecisionStyleTestCase(
            description="forced replace is bold yellow",
            decision=MigrationDecision.FORCED_REPLACE,
            compatibility=MigrationCompatibility.COMPATIBLE,
            findings=(),
            expected_fragments=(f"{_BOLD_YELLOW}forced replace{_RESET}",),
        ),
        MigrationDecisionStyleTestCase(
            description="conflict is bold red with red incompatibility and blocking reason",
            decision=MigrationDecision.CONFLICT,
            compatibility=MigrationCompatibility.INCOMPATIBLE,
            findings=("column amount_cents changed type",),
            expected_fragments=(
                f"{_BOLD_RED}conflict{_RESET}",
                f"    {_DIM}compatibility{_RESET}  {_RED}incompatible{_RESET}",
                f"    {_RED}! column amount_cents changed type{_RESET}",
            ),
        ),
        MigrationDecisionStyleTestCase(
            description="origin missing is bold red",
            decision=MigrationDecision.ORIGIN_MISSING,
            compatibility=MigrationCompatibility.NOT_CHECKED,
            findings=(),
            expected_fragments=(f"{_BOLD_RED}origin missing{_RESET}",),
        ),
        MigrationDecisionStyleTestCase(
            description="renamed hands over identity with dim origin and note",
            decision=MigrationDecision.RENAMED,
            compatibility=MigrationCompatibility.NOT_CHECKED,
            findings=(),
            expected_fragments=(
                f"\033[1mRenamed{_RESET} {_DIM}(1){_RESET}",
                f"  daily_revenue  {_DIM}prod.revenue ->{_RESET} prod.daily_revenue  "
                f"{_DIM}(identity handed over){_RESET}",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_migration_decision_when_formatting_then_applies_colour_roles(
    test_case: MigrationDecisionStyleTestCase,
) -> None:
    rendered: str = styled_migration_text(
        migration_entry(
            decision=test_case.decision,
            compatibility=test_case.compatibility,
            findings=test_case.findings,
        )
    )

    assert all(fragment in rendered for fragment in test_case.expected_fragments), rendered


@pytest.mark.parametrize(
    "test_case",
    (
        MigrationPlainTextTestCase(
            description="colour off keeps the migration tree wording unchanged",
            decision=MigrationDecision.MIGRATE,
            expected_text=(
                "Migrations (1)\n"
                "└── daily_revenue  migrate  prod.revenue -> prod.daily_revenue\n"
                "    ├── compatibility  compatible\n"
                "    ├── transfer  physical copy, promote by transactional rename\n"
                "    └── discovery  automatic"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_colour_off_when_formatting_plan_then_migration_text_is_plain(
    test_case: MigrationPlainTextTestCase,
) -> None:
    rendered: str = format_plan(
        plan=PlanOutput(migration_entries=(migration_entry(decision=test_case.decision),)),
        use_color=False,
        include_header=False,
    )

    assert rendered.strip("\n") == test_case.expected_text
    assert "\033[" not in rendered


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
