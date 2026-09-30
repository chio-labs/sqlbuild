"""Migration plan text colour roles and plain rendering."""

from __future__ import annotations

import pytest

from sqlbuild.cli.output.main.plan import format_plan
from sqlbuild.compiler.migrations.types import (
    ColumnMigrationDecision,
    MigrationCompatibility,
    MigrationDecision,
    MigrationDiscovery,
)
from sqlbuild.compiler.planner.main.pre_build.pre_build_work_display import format_pre_build_work
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.presentation.models import DisplayOptions
from tests.unit.src.sqlbuild.compiler.planner.main.pre_build._test_types import (
    ColumnMigrationPlainTextTestCase,
    ColumnMigrationStyleTestCase,
    MigrationDecisionStyleTestCase,
    MigrationPlainTextTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.main.pre_build.helpers import (
    column_migration_entry,
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
            description="origin missing allowed by the default policy is bold yellow",
            decision=MigrationDecision.ORIGIN_MISSING,
            compatibility=MigrationCompatibility.NOT_CHECKED,
            findings=(),
            expected_fragments=(f"{_BOLD_YELLOW}origin missing{_RESET}",),
        ),
        MigrationDecisionStyleTestCase(
            description="renamed table is listed as a bold blue migration that rebuilds it",
            decision=MigrationDecision.RENAMED,
            compatibility=MigrationCompatibility.NOT_CHECKED,
            findings=(),
            expected_fragments=(
                f"\033[1mMigrations{_RESET} {_DIM}(1){_RESET}",
                f"  daily_revenue  {_BOLD_BLUE}migrate{_RESET}  {_DIM}prod.revenue ->{_RESET} "
                "prod.daily_revenue",
                f"    {_DIM}transfer{_RESET}  rebuild (table)",
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
                "    ├── discovery  automatic\n"
                "    └── hint  matched by unchanged definition; sqb rename model:<old> <new> "
                "also rewrites references and adds migrate_from when discovery cannot match"
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


@pytest.mark.parametrize(
    "test_case",
    (
        ColumnMigrationPlainTextTestCase(
            description="one pending rename renders as the column migration tree",
            entries=(
                (
                    "fact_orders",
                    "amount",
                    "revenue",
                    ColumnMigrationDecision.RENAME,
                    MigrationDiscovery.MANUAL,
                ),
            ),
            expected_text=(
                "Column migrations (1)\n"
                "└── fact_orders  migrate columns\n"
                "    └── amount -> revenue  rename in place"
            ),
        ),
        ColumnMigrationPlainTextTestCase(
            description="renames group under each model and mark automatic discovery",
            entries=(
                (
                    "fact_orders",
                    "amount",
                    "revenue",
                    ColumnMigrationDecision.RENAME,
                    MigrationDiscovery.AUTOMATIC,
                ),
                (
                    "fact_orders",
                    "tax",
                    "tax_amount",
                    ColumnMigrationDecision.RECORD,
                    MigrationDiscovery.MANUAL,
                ),
                (
                    "order_history",
                    "status",
                    "order_status",
                    ColumnMigrationDecision.RENAME,
                    MigrationDiscovery.MANUAL,
                ),
            ),
            expected_text=(
                "Column migrations (3)\n"
                "├── fact_orders  migrate columns\n"
                "    ├── amount -> revenue  rename in place  (automatic)\n"
                "    └── tax -> tax_amount  already renamed, record\n"
                "└── order_history  migrate columns\n"
                "    └── status -> order_status  rename in place"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_column_migrations_when_formatting_plan_then_renders_a_model_tree(
    test_case: ColumnMigrationPlainTextTestCase,
) -> None:
    rendered: str = format_plan(
        plan=PlanOutput(
            column_migration_entries=tuple(
                column_migration_entry(
                    model_name=model_name,
                    origin_column=origin,
                    destination_column=destination,
                    decision=decision,
                    discovery=discovery,
                )
                for model_name, origin, destination, decision, discovery in test_case.entries
            )
        ),
        use_color=False,
        include_header=False,
    )

    assert rendered.strip("\n") == test_case.expected_text


@pytest.mark.parametrize(
    "test_case",
    (
        ColumnMigrationStyleTestCase(
            description="pending rename is bold blue",
            decision=ColumnMigrationDecision.RENAME,
            expected_fragment=f"{_BOLD_BLUE}rename in place{_RESET}",
        ),
        ColumnMigrationStyleTestCase(
            description="done is dim",
            decision=ColumnMigrationDecision.DONE,
            expected_fragment=f"{_DIM}done{_RESET}",
        ),
        ColumnMigrationStyleTestCase(
            description="conflict is bold red",
            decision=ColumnMigrationDecision.CONFLICT,
            expected_fragment=f"{_BOLD_RED}conflict{_RESET}",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_column_migration_decision_when_formatting_then_applies_colour_roles(
    test_case: ColumnMigrationStyleTestCase,
) -> None:
    rendered: str = "\n".join(
        format_pre_build_work(
            lines=[],
            plan=PlanOutput(
                column_migration_entries=(
                    column_migration_entry(
                        model_name="fact_orders",
                        origin_column="amount",
                        destination_column="revenue",
                        decision=test_case.decision,
                        discovery=MigrationDiscovery.MANUAL,
                    ),
                )
            ),
            display_options=DisplayOptions(),
        )
    )

    assert f"\033[1mColumn migrations{_RESET} {_DIM}(1){_RESET}" in rendered
    assert test_case.expected_fragment in rendered, rendered


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
