from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.clone.output import (
    render_clone_item_line,
    render_clone_output,
)
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from tests.unit.src.sqlbuild.cli.commands._helpers.clone._test_types import (
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
                    CloneItemResult(
                        name="add_tax",
                        action=CloneAction.RECREATED_FUNCTION,
                        status=CloneStatus.SUCCESS,
                    ),
                )
            ),
            expected_fragments=(
                "stg_orders",
                "missing in origin environment",
                "dim_customers",
                "boom",
                "RECREATED_FUNCTIONS=1",
                "\u2717 Completed with errors",
            ),
            expected_color_fragments=(
                "\033[38;5;167m\u2717\033[0m \033[38;5;167m\033[1mCompleted with errors\033[0m",
                "\033[2mCLONED=\033[0m\033[34m1\033[0m",
                "\033[2mPASS=\033[0m\033[32m2\033[0m",
                "\033[2mWARN=\033[0m\033[33m1\033[0m",
                "\033[2mFAIL=\033[0m\033[38;5;167m1\033[0m",
            ),
            unexpected_fragments=("fact_orders", "add_tax"),
        ),
    ],
    ids=lambda case: case.description,
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
                origin_relation="PROD.MAIN.FACT_ORDERS",
                destination_relation="DEV.MAIN.FACT_ORDERS",
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
            relation_width=50,
            expected_line=(
                "  2/5  copied                      "
                "prod.main.fact_orders -> dev.main.fact_orders       OK  0.42s"
            ),
            unexpected_fragments=("PROD.MAIN.FACT_ORDERS", "DEV.MAIN.FACT_ORDERS"),
        ),
        RenderCloneItemLineTestCase(
            description="mixed quoted relation names preserve quoted case",
            index=5,
            total=5,
            item=CloneItemResult(
                name="orders",
                action=CloneAction.CLONED,
                status=CloneStatus.SUCCESS,
                origin_relation='PROD.MAIN."Orders"',
                destination_relation='DEV.MAIN."Orders"',
            ),
            expected_fragments=('prod.main."Orders"', 'dev.main."Orders"'),
            expected_line=(
                '  5/5  cloned                      prod.main."Orders" -> dev.main."Orders"  OK'
            ),
            unexpected_fragments=("PROD.MAIN", "DEV.MAIN"),
        ),
        RenderCloneItemLineTestCase(
            description="escaped bracket identifier preserves quoted case",
            index=5,
            total=5,
            item=CloneItemResult(
                name="orders",
                action=CloneAction.CLONED,
                status=CloneStatus.SUCCESS,
                origin_relation="PROD.DBO.[My]]Table]",
                destination_relation="DEV.DBO.[My]]Table]",
            ),
            expected_fragments=("prod.dbo.[My]]Table]", "dev.dbo.[My]]Table]"),
            expected_line=(
                "  5/5  cloned                      prod.dbo.[My]]Table] -> dev.dbo.[My]]Table]  OK"
            ),
            unexpected_fragments=("[My]]table]",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_item_when_rendering_line_then_shows_flow_and_status(
    test_case: RenderCloneItemLineTestCase,
) -> None:
    line: str = render_clone_item_line(
        index=test_case.index,
        total=test_case.total,
        item=test_case.item,
        use_color=False,
        relation_width=test_case.relation_width,
    )

    assert line == test_case.expected_line
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in line
    for fragment in test_case.unexpected_fragments:
        assert fragment not in line
