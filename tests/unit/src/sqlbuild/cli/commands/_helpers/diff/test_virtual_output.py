from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.diff.virtual_output import format_virtual_diff_header
from sqlbuild.cli.commands.models import VirtualDiffRunOutcome
from sqlbuild.executor.diff.models import DiffExecutionResult
from tests.unit.src.sqlbuild.cli.commands._helpers.diff._test_types import (
    RenderVirtualDiffHeaderTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderVirtualDiffHeaderTestCase(
            description="renders compact no color layout with unchanged ref count",
            selected_names=("dim_customers", "fact_orders", "stg_orders"),
            skipped_names=("dim_customers",),
            from_stale=("fact_orders", "stg_orders"),
            to_stale=(),
            from_working=True,
            to_working=False,
            allow_partial_diff=True,
            verbose=False,
            expected_fragments=(
                "Virtual diff  dev -> pr",
                "selected models         3",
                "compared models         2",
                "unchanged refs skipped  1",
                "working VDEs            yes (partial allowed)",
            ),
            expected_color_fragments=(
                "\033[34m\033[1mVirtual diff\033[0m",
                "dev -> pr",
                "selected models         \033[34m3\033[0m",
                "unchanged refs skipped  \033[2m1\033[0m",
                "working VDEs            \033[33m\033[1myes\033[0m\033[2m (partial allowed)\033[0m",
            ),
            unexpected_fragments=("not current with workspace",),
        ),
        RenderVirtualDiffHeaderTestCase(
            description="verbose renders workspace staleness details",
            selected_names=("dim_customers", "fact_orders", "stg_orders"),
            skipped_names=(),
            from_stale=("fact_orders",),
            to_stale=("stg_orders",),
            from_working=False,
            to_working=False,
            allow_partial_diff=False,
            verbose=True,
            expected_fragments=(
                "compared models         3",
                "working VDEs            no",
                "dev not current with workspace: fact_orders",
                "pr not current with workspace: stg_orders",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_diff_metadata_when_formatting_header_then_expected_details_render(
    test_case: RenderVirtualDiffHeaderTestCase,
) -> None:
    outcome: VirtualDiffRunOutcome = VirtualDiffRunOutcome(
        result=DiffExecutionResult(),
        selected_names=test_case.selected_names,
        skipped_names=test_case.skipped_names,
        from_stale=test_case.from_stale,
        to_stale=test_case.to_stale,
        from_working=test_case.from_working,
        to_working=test_case.to_working,
    )
    result: str = format_virtual_diff_header(
        from_virtual_environment="dev",
        to_virtual_environment="pr",
        outcome=outcome,
        allow_partial_diff=test_case.allow_partial_diff,
        verbose=test_case.verbose,
        use_color=False,
    )
    color_result: str = format_virtual_diff_header(
        from_virtual_environment="dev",
        to_virtual_environment="pr",
        outcome=outcome,
        allow_partial_diff=test_case.allow_partial_diff,
        verbose=test_case.verbose,
        use_color=True,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result
    for fragment in test_case.expected_color_fragments:
        assert fragment in color_result
