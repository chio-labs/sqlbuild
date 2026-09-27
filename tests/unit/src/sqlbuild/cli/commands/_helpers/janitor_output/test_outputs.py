"""Janitor completion summary wording."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from sqlbuild.cli.commands._helpers.janitor_output.outputs import write_janitor_completion
from sqlbuild.cli.commands.models import JanitorInvocation
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
            description="single archive and object use singular nouns",
            archived=1,
            deleted=1,
            pruned_direct_state=0,
            expected_output="Archived 1 relation. Deleted 1 object.\n",
        ),
        JanitorCompletionTestCase(
            description="single pruned state table uses a singular noun",
            archived=0,
            deleted=0,
            pruned_direct_state=1,
            expected_output="Deleted 0 objects and pruned 1 direct state table.\n",
        ),
        JanitorCompletionTestCase(
            description="plural counts keep plural nouns",
            archived=2,
            deleted=3,
            pruned_direct_state=2,
            expected_output=(
                "Archived 2 relations. Deleted 3 objects and pruned 2 direct state tables.\n"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_janitor_counts_when_writing_completion_then_nouns_match_counts(
    test_case: JanitorCompletionTestCase, capsys: pytest.CaptureFixture[str]
) -> None:
    result: JanitorExecutionResult = JanitorExecutionResult(
        archived=placeholder_candidates(test_case.archived),
        deleted=placeholder_candidates(test_case.deleted),
        pruned_direct_state=placeholder_candidates(test_case.pruned_direct_state),
    )

    write_janitor_completion(
        invocation=cast(JanitorInvocation, SimpleNamespace(use_color=False)), result=result
    )

    assert capsys.readouterr().out == test_case.expected_output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
