"""Tests for the janitor plan preview."""

from __future__ import annotations

import pytest

from sqlbuild._native import render_janitor_plan
from sqlbuild.executor.janitor.models import JanitorPlan
from tests.unit.src.sqlbuild.cli.commands.main.janitor._test_types import (
    JanitorPlanOutputTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.janitor.helpers import (
    build_direct_archive_plan,
    build_janitor_plan,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPlanOutputTestCase(
            description="preserves no-color plan fragments",
            use_color=False,
            expected_output_fragments=(
                "Janitor preview  dev",
                "  retention              30 days",
                "  relations to archive   0",
                "Janitor blocked\n  Managed target schemas contain active configured sources.",
                "blocked  active sources: raw.events",
                "suppressed archive: blocked.old_model",
                "No janitor actions will be performed.",
                "Skipped schemas\n  dev  contains active source raw.orders",
                "Skipped objects (1)\n  1  source relation",
            ),
            unexpected_output_fragments=(
                "\033[",
                "checkpoints pruned",
                "VDEs pruned",
                "virtual state pruned",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_janitor_plan_when_writing_without_color_then_preserves_output_fragments(
    test_case: JanitorPlanOutputTestCase,
) -> None:
    plan: JanitorPlan = build_janitor_plan()
    output: str = render_janitor_plan(plan=plan, use_color=test_case.use_color)
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_output_fragments:
        assert fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPlanOutputTestCase(
            description="uses semantic plan colors",
            use_color=True,
            expected_output_fragments=(
                "\033[34m\033[1mJanitor preview\033[0m",
                "dev",
                "\033[34m30 days\033[0m",
                "relations to archive   \033[34m0\033[0m",
                "Janitor blocked",
                "\033[2msource relation\033[0m",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_janitor_plan_when_writing_with_color_then_uses_semantic_colors(
    test_case: JanitorPlanOutputTestCase,
) -> None:
    plan: JanitorPlan = build_janitor_plan()
    output: str = render_janitor_plan(plan=plan, use_color=test_case.use_color)
    for fragment in test_case.expected_output_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPlanOutputTestCase(
            description="direct preview lists exact archive names, ages, and expiry",
            use_color=False,
            expected_output_fragments=(
                "  retention              14 days",
                "  archive retention      14 days",
                "  relations to archive   1",
                "  archives to delete     1",
                "  archives retained      0",
                "Relations to archive\n  dev.old_orders  ->  "
                "dev._sqb_archive__20260924t101500z__old_orders  "
                "age 20d, delete after 2026-10-08 10:15:00 UTC",
                "Archives to delete\n  dev._sqb_archive__20260101t000000z__old_products  "
                "archived 2026-01-01 00:00:00 UTC, age 266d, expired 2026-01-15 00:00:00 UTC",
            ),
            unexpected_output_fragments=("eligible for deletion", "Eligible objects"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_archive_plan_when_writing_preview_then_lists_archive_actions(
    test_case: JanitorPlanOutputTestCase,
) -> None:
    output: str = render_janitor_plan(
        plan=build_direct_archive_plan(), use_color=test_case.use_color
    )
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_output_fragments:
        assert fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPlanOutputTestCase(
            description="verbose preview lists each skipped object with its reason",
            use_color=False,
            expected_output_fragments=("Skipped objects\n  dev.source_table  source relation",),
            unexpected_output_fragments=("Skipped objects (1)",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_janitor_plan_when_writing_verbose_preview_then_lists_every_skipped_object(
    test_case: JanitorPlanOutputTestCase,
) -> None:
    output: str = render_janitor_plan(
        plan=build_janitor_plan(), use_color=test_case.use_color, verbose=True
    )
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_output_fragments:
        assert fragment not in output
