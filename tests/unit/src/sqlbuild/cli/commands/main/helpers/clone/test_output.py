from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.clone.output import render_clone_output
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from tests.unit.src.sqlbuild.cli.commands.main.helpers.clone._test_types import (
    RenderCloneOutputTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderCloneOutputTestCase(
            description="styles clone status rows semantically",
            result=CloneExecutionResult(
                item_results=(
                    CloneItemResult(
                        name="fact_orders",
                        action=CloneAction.CLONED,
                        status=CloneStatus.SUCCESS,
                    ),
                    CloneItemResult(
                        name="stg_orders",
                        action=CloneAction.WARNING_MISSING_SOURCE,
                        status=CloneStatus.WARNING,
                    ),
                    CloneItemResult(
                        name="dim_customers",
                        action=CloneAction.FAILED,
                        status=CloneStatus.FAILED,
                    ),
                )
            ),
            expected_fragments=(
                "sqb clone  from=prod to=dev",
                "fact_orders",
                "OK",
                "WARN",
                "FAIL",
            ),
            expected_color_fragments=(
                "\033[32mOK\033[0m",
                "\033[33mWARN\033[0m",
                "\033[31mFAIL\033[0m",
            ),
        ),
    ],
    ids=["styles clone status rows semantically"],
)
def test_given_clone_result_when_rendering_then_styles_status_rows(
    test_case: RenderCloneOutputTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    render_clone_output(
        result=test_case.result,
        from_target="prod",
        to_target="dev",
        use_color=False,
    )
    no_color_output: str = capsys.readouterr().out

    render_clone_output(
        result=test_case.result,
        from_target="prod",
        to_target="dev",
        use_color=True,
    )
    color_output: str = capsys.readouterr().out

    for fragment in test_case.expected_fragments:
        assert fragment in no_color_output
    assert "\033[" not in no_color_output
    for fragment in test_case.expected_color_fragments:
        assert fragment in color_output
