"""Tests for bounded inline error rendering."""

from __future__ import annotations

import pytest

from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.inline_error_lines import format_inline_error_lines
from tests.unit.src.sqlbuild.presentation.main._test_types import InlineErrorLinesTestCase


@pytest.mark.parametrize(
    "test_case",
    (
        InlineErrorLinesTestCase(
            description="one-column content keeps truncation marker within width",
            content_width=1,
            expected_lines=["a", "."],
        ),
        InlineErrorLinesTestCase(
            description="wide content wraps twice before using an ellipsis",
            content_width=8,
            expected_lines=["abcdefgh", "ijklm..."],
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_content_width_when_formatting_inline_error_then_bounds_each_line(
    test_case: InlineErrorLinesTestCase,
) -> None:
    lines: list[str] = format_inline_error_lines(
        error_code=None,
        error_message="abcdefghijklmnopqrstuvwxyz",
        error_help=None,
        content_width=test_case.content_width,
        style=CliStyle(use_color=False),
    )

    assert lines == test_case.expected_lines
