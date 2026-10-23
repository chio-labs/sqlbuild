"""Janitor completion line wording."""

from __future__ import annotations

import pytest

from sqlbuild._native import render_janitor_completion
from sqlbuild.executor.janitor.models import JanitorExecutionResult
from tests.unit.src.sqlbuild.cli.commands._helpers.janitor_output._test_types import (
    JanitorCompletionTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.janitor_output.helpers import (
    placeholder_candidates,
)


@pytest.mark.parametrize(
    "test_case",
    (
        JanitorCompletionTestCase(
            description="counts archived, deleted and pruned items",
            archived=1,
            deleted=1,
            pruned_direct_state=0,
            expected_output="\u2713 Janitor completed  archived 1, deleted 1, pruned 0\n",
        ),
        JanitorCompletionTestCase(
            description="zero counts stay visible",
            archived=0,
            deleted=0,
            pruned_direct_state=1,
            expected_output="\u2713 Janitor completed  archived 0, deleted 0, pruned 1\n",
        ),
        JanitorCompletionTestCase(
            description="elapsed time follows the counts",
            archived=2,
            deleted=3,
            pruned_direct_state=2,
            elapsed_seconds=302.4,
            expected_output="\u2713 Janitor completed  archived 2, deleted 3, pruned 2  (5m 02s)\n",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_janitor_counts_when_writing_completion_then_line_reports_totals(
    test_case: JanitorCompletionTestCase,
) -> None:
    result: JanitorExecutionResult = JanitorExecutionResult(
        archived=placeholder_candidates(test_case.archived),
        deleted=placeholder_candidates(test_case.deleted),
        pruned_direct_state=placeholder_candidates(test_case.pruned_direct_state),
    )

    output: str = render_janitor_completion(
        result=result, elapsed_seconds=test_case.elapsed_seconds, use_color=False
    )

    assert output == test_case.expected_output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
