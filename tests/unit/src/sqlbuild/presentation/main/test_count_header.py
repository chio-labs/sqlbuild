from __future__ import annotations

import pytest

from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.count_header import count_header_style
from tests.unit.src.sqlbuild.presentation.main._test_types import CountHeaderTestCase


@pytest.mark.parametrize(
    "test_case",
    (
        CountHeaderTestCase(
            description="counted header renders a bold title and a dim count",
            text="Models (3)",
            use_color=True,
            expected_rendered="\033[1mModels\033[0m \033[2m(3)\033[0m",
        ),
        CountHeaderTestCase(
            description="page summary in parentheses is dimmed as the count",
            text="Available (2 of 5, 3 collapsed)",
            use_color=True,
            expected_rendered="\033[1mAvailable\033[0m \033[2m(2 of 5, 3 collapsed)\033[0m",
        ),
        CountHeaderTestCase(
            description="header without a count is only bold",
            text="Providers",
            use_color=True,
            expected_rendered="\033[1mProviders\033[0m",
        ),
        CountHeaderTestCase(
            description="color off keeps the header text unchanged",
            text="Migrations (1)",
            use_color=False,
            expected_rendered="Migrations (1)",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_header_text_when_styling_then_title_is_bold_and_count_is_dim(
    test_case: CountHeaderTestCase,
) -> None:
    style: CliStyle = CliStyle(use_color=test_case.use_color)

    rendered: str = count_header_style(style=style, title_style=style.plan_section)(test_case.text)

    assert rendered == test_case.expected_rendered


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
