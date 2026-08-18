"""Tests for coded error rendering."""

from __future__ import annotations

import pytest

from sqlbuild.presentation.main.coded_error_text import format_coded_error
from tests.unit.src.sqlbuild.presentation.main._test_types import FormatCodedErrorTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCodedErrorTestCase(
            description="renders plain coded error",
            code="R002",
            message="materialization failed",
            help=None,
            use_color=False,
            expected_rendered="error[R002]: materialization failed",
        ),
        FormatCodedErrorTestCase(
            description="renders coded detail beneath an existing error label",
            code="T002",
            message="test execution failed",
            help=None,
            use_color=False,
            expected_rendered="[T002] test execution failed",
            include_error_label=False,
        ),
        FormatCodedErrorTestCase(
            description="renders plain coded error with help",
            code="K011",
            message="contract requires staged promotion",
            help="set table_promotion_mode to staged",
            use_color=False,
            expected_rendered=(
                "error[K011]: contract requires staged promotion\n"
                "  = help: set table_promotion_mode to staged"
            ),
        ),
        FormatCodedErrorTestCase(
            description="renders colorized coded error with help",
            code="R006",
            message="audit failed",
            help="fix failing audit rows",
            use_color=True,
            expected_rendered=(
                "\033[38;5;167m\033[1merror[R006]:\033[0m audit failed\n"
                "  \033[2m= help:\033[0m fix failing audit rows"
            ),
        ),
        FormatCodedErrorTestCase(
            description="renders multiline coded error without color unchanged",
            code="D012",
            message=(
                "Provider 'slack_provider' in providers/slack.py has invalid settings:\n"
                "1 validation error for SlackProvider\n"
                "SLACK_TOKEN"
            ),
            help=None,
            use_color=False,
            expected_rendered=(
                "error[D012]: Provider 'slack_provider' in providers/slack.py has invalid settings:\n"
                "1 validation error for SlackProvider\n"
                "SLACK_TOKEN"
            ),
        ),
        FormatCodedErrorTestCase(
            description="renders multiline coded error with muted continuation lines",
            code="D012",
            message=(
                "Provider 'slack_provider' in providers/slack.py has invalid settings:\n"
                "1 validation error for SlackProvider\n"
                "SLACK_TOKEN"
            ),
            help=None,
            use_color=True,
            expected_rendered=(
                "\033[38;5;167m\033[1merror[D012]:\033[0m "
                "Provider 'slack_provider' in providers/slack.py has invalid settings:\n"
                "\033[2m1 validation error for SlackProvider\033[0m\n"
                "\033[2mSLACK_TOKEN\033[0m"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_coded_error_when_formatting_then_renders_consistently(
    test_case: FormatCodedErrorTestCase,
) -> None:
    rendered: str = format_coded_error(
        code=test_case.code,
        message=test_case.message,
        help=test_case.help,
        use_color=test_case.use_color,
        include_error_label=test_case.include_error_label,
    )

    assert rendered == test_case.expected_rendered
