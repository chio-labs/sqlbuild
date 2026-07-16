from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.rollback.output import format_rollback_output
from tests.unit.src.sqlbuild.cli.commands._helpers.rollback._test_types import (
    FormatRollbackOutputTestCase,
)

ROLLED_BACK_MODELS: tuple[str, ...] = tuple(f"model_{index:02d}" for index in range(25))


@pytest.mark.parametrize(
    "test_case",
    [
        FormatRollbackOutputTestCase(
            description="renders finalized rollback with capped model set",
            status="finalized",
            rolled_back_models=ROLLED_BACK_MODELS,
            verbose=False,
            expected_fragments=(
                "Virtual rollback complete",
                "virtual environment  dev",
                "checkpoint           cp_123",
                "status               finalized",
                "rolled back models   25",
                "rolled back model set: model_00",
                "... 5 more; use --verbose to show all",
            ),
            expected_color_fragments=(
                "\033[32m\033[1mVirtual rollback complete\033[0m",
                "virtual environment  \033[34m\033[1mdev\033[0m",
                "checkpoint           \033[34m\033[1mcp_123\033[0m",
                "status               \033[32m\033[1mfinalized\033[0m",
                "rolled back models   \033[34m\033[1m25\033[0m",
                "\033[2mrolled back model set\033[0m: model_00",
            ),
            unexpected_fragments=("model_24",),
        ),
        FormatRollbackOutputTestCase(
            description="verbose rollback shows uncapped model set",
            status="working",
            rolled_back_models=ROLLED_BACK_MODELS,
            verbose=True,
            expected_fragments=("status               working", "model_24"),
            unexpected_fragments=("use --verbose",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rollback_summary_when_formatting_then_output_is_capped_and_status_is_clear(
    test_case: FormatRollbackOutputTestCase,
) -> None:
    result: str = format_rollback_output(
        virtual_environment="dev",
        checkpoint_id="cp_123",
        status=test_case.status,
        rolled_back_models=test_case.rolled_back_models,
        verbose=test_case.verbose,
        use_color=False,
    )
    color_result: str = format_rollback_output(
        virtual_environment="dev",
        checkpoint_id="cp_123",
        status=test_case.status,
        rolled_back_models=test_case.rolled_back_models,
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
