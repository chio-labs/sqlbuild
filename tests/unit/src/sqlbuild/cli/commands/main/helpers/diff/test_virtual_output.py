from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.diff.virtual_output import format_virtual_diff_header
from tests.unit.src.sqlbuild.cli.commands.main.helpers.diff._test_types import (
    RenderVirtualDiffHeaderTestCase,
)

TEST_CASES: list[RenderVirtualDiffHeaderTestCase] = [
    RenderVirtualDiffHeaderTestCase(
        description="renders compact no color layout with unchanged ref count",
        selected_names=("dim_customers", "fact_orders", "stg_orders"),
        skipped_names=("dim_customers",),
        from_stale=("fact_orders", "stg_orders"),
        to_stale=(),
        allow_partial_diff=True,
        verbose=False,
        expected_fragments=(
            "Virtual diff  dev -> pr",
            "selected models         3",
            "compared models         2",
            "unchanged refs skipped  1",
            "working VDEs            yes (partial allowed)",
        ),
        unexpected_fragments=("not current with workspace",),
    ),
    RenderVirtualDiffHeaderTestCase(
        description="verbose renders workspace staleness details",
        selected_names=("dim_customers", "fact_orders", "stg_orders"),
        skipped_names=(),
        from_stale=("fact_orders",),
        to_stale=("stg_orders",),
        allow_partial_diff=False,
        verbose=True,
        expected_fragments=(
            "compared models         3",
            "dev not current with workspace: fact_orders",
            "pr not current with workspace: stg_orders",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_virtual_diff_metadata_when_formatting_header_then_expected_details_render(
    test_case: RenderVirtualDiffHeaderTestCase,
) -> None:
    result: str = format_virtual_diff_header(
        from_virtual_environment="dev",
        to_virtual_environment="pr",
        selected_names=test_case.selected_names,
        skipped_names=test_case.skipped_names,
        from_stale=test_case.from_stale,
        to_stale=test_case.to_stale,
        allow_partial_diff=test_case.allow_partial_diff,
        verbose=test_case.verbose,
        use_color=False,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result
