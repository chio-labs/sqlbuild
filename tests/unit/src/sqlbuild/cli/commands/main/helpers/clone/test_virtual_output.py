from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.clone.virtual_output import render_virtual_clone_output
from tests.unit.src.sqlbuild.cli.commands.main.helpers.clone._test_types import (
    RenderVirtualCloneOutputTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.helpers.clone.helpers import (
    build_virtual_clone_result,
)

VIRTUAL_CLONE_OUTPUT_TEST_CASES: tuple[RenderVirtualCloneOutputTestCase, ...] = (
    RenderVirtualCloneOutputTestCase(
        description="caps missing and skipped model sets by default",
        result=build_virtual_clone_result(missing_count=22, skipped_count=21),
        verbose=False,
        expected_fragments=(
            "Virtual clone  prod -> dev",
            "source state         not used",
            "target refs          unchanged",
            "missing_19",
            "skipped_19",
            "... 2 more; use --verbose to show all",
            "... 1 more; use --verbose to show all",
        ),
        unexpected_fragments=("missing_20", "skipped_20"),
    ),
    RenderVirtualCloneOutputTestCase(
        description="verbose output shows full missing and skipped model sets",
        result=build_virtual_clone_result(missing_count=22, skipped_count=21),
        verbose=True,
        expected_fragments=("missing_21", "skipped_20"),
        unexpected_fragments=("use --verbose",),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    VIRTUAL_CLONE_OUTPUT_TEST_CASES,
    ids=[case.description for case in VIRTUAL_CLONE_OUTPUT_TEST_CASES],
)
def test_given_virtual_clone_result_when_rendering_then_output_respects_caps(
    test_case: RenderVirtualCloneOutputTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    render_virtual_clone_output(result=test_case.result, use_color=False, verbose=test_case.verbose)

    output: str = capsys.readouterr().out
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output
