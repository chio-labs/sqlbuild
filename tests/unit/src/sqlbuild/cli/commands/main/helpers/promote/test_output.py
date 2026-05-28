from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.promote.output import format_promote_output
from tests.unit.src.sqlbuild.cli.commands.main.helpers.promote._test_types import (
    FormatPromoteOutputTestCase,
)

PROMOTED_MODELS: tuple[str, ...] = tuple(f"model_{index:02d}" for index in range(25))

TEST_CASES: list[FormatPromoteOutputTestCase] = [
    FormatPromoteOutputTestCase(
        description="renders finalized promotion with capped model set",
        status="finalized",
        promoted_models=PROMOTED_MODELS,
        remaining_stale=(),
        verbose=False,
        expected_fragments=(
            "Virtual promotion complete  pr -> dev",
            "target status          finalized",
            "promoted models        25",
            "promoted model set: model_00",
            "... 5 more; use --verbose to show all",
            "remaining stale models 0",
        ),
        unexpected_fragments=("model_24",),
    ),
    FormatPromoteOutputTestCase(
        description="verbose renders uncapped model set",
        status="working",
        promoted_models=PROMOTED_MODELS,
        remaining_stale=("orders_rollup",),
        verbose=True,
        expected_fragments=(
            "target status          working",
            "promoted model set: model_00",
            "model_24",
            "remaining stale models 1",
            "remaining stale set: orders_rollup",
        ),
        unexpected_fragments=("use --verbose",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_promotion_summary_when_formatting_then_output_is_capped_and_status_is_clear(
    test_case: FormatPromoteOutputTestCase,
) -> None:
    result: str = format_promote_output(
        from_virtual_environment="pr",
        to_virtual_environment="dev",
        status=test_case.status,
        promoted_models=test_case.promoted_models,
        remaining_stale=test_case.remaining_stale,
        verbose=test_case.verbose,
        use_color=False,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result
