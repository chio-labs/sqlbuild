from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.clone.output import (
    render_clone_item_line,
    render_clone_output,
)
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from tests.unit.src.sqlbuild.cli.commands.main.helpers.clone._test_types import (
    RenderCloneItemLineTestCase,
    RenderCloneOutputTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderCloneOutputTestCase(
            description="summary footer reports counts and surfaces non-success messages",
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
                        message="missing in origin environment",
                    ),
                    CloneItemResult(
                        name="dim_customers",
                        action=CloneAction.FAILED,
                        status=CloneStatus.FAILED,
                        message="boom",
                    ),
                )
            ),
            expected_fragments=(
                "stg_orders",
                "missing in origin environment",
                "dim_customers",
                "boom",
                "Completed with warnings.",
            ),
            expected_color_fragments=(
                "\033[33m\033[1mCompleted with warnings.\033[0m",
                "\033[2mCLONED=\033[0m\033[34m\033[1m1\033[0m",
                "\033[2mPASS=\033[0m\033[32m1\033[0m",
                "\033[2mWARN=\033[0m\033[33m1\033[0m",
                "\033[2mFAIL=\033[0m\033[31m1\033[0m",
            ),
            unexpected_fragments=("fact_orders",),
        ),
    ],
    ids=["summary footer reports counts and surfaces non-success messages"],
)
def test_given_clone_result_when_rendering_summary_then_reports_footer_and_messages(
    test_case: RenderCloneOutputTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    render_clone_output(result=test_case.result, use_color=False)
    no_color_output: str = capsys.readouterr().out

    render_clone_output(result=test_case.result, use_color=True)
    color_output: str = capsys.readouterr().out

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in no_color_output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in no_color_output
    assert "\033[" not in no_color_output
    for fragment in test_case.expected_color_fragments:
        assert fragment in color_output


@pytest.mark.parametrize(
    "test_case",
    [
        RenderCloneItemLineTestCase(
            description="streamed line shows position, action, origin->destination and status",
            index=2,
            total=5,
            item=CloneItemResult(
                name="fact_orders",
                action=CloneAction.COPIED,
                status=CloneStatus.SUCCESS,
                origin_relation="prod.main.fact_orders",
                destination_relation="dev.main.fact_orders",
                duration_seconds=0.42,
            ),
            expected_fragments=(
                "2/5",
                "copied",
                "prod.main.fact_orders",
                "->",
                "dev.main.fact_orders",
                "OK",
                "0.42s",
            ),
        )
    ],
    ids=["streamed line shows position, action, origin->destination and status"],
)
def test_given_clone_item_when_rendering_line_then_shows_flow_and_status(
    test_case: RenderCloneItemLineTestCase,
) -> None:
    line: str = render_clone_item_line(
        index=test_case.index,
        total=test_case.total,
        item=test_case.item,
        use_color=False,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in line
    for fragment in test_case.unexpected_fragments:
        assert fragment not in line
