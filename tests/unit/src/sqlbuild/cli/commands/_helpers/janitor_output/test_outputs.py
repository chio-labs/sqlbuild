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
            deleted_state_backups=0,
            deleted_checkpoints=0,
            pruned_direct_state=0,
            expected_output="Archived 1 relation. Deleted 1 object.\n",
        ),
        JanitorCompletionTestCase(
            description="single state item and pruned table use singular nouns",
            archived=0,
            deleted=0,
            deleted_state_backups=1,
            deleted_checkpoints=0,
            pruned_direct_state=1,
            expected_output=(
                "Deleted 0 objects, deleted 1 state item, and pruned 1 direct state table.\n"
            ),
        ),
        JanitorCompletionTestCase(
            description="single checkpoint uses a singular noun",
            archived=2,
            deleted=2,
            deleted_state_backups=0,
            deleted_checkpoints=1,
            pruned_direct_state=0,
            expected_output="Archived 2 relations. Deleted 2 objects and 1 checkpoint.\n",
        ),
        JanitorCompletionTestCase(
            description="plural counts keep plural nouns",
            archived=0,
            deleted=3,
            deleted_state_backups=2,
            deleted_checkpoints=0,
            pruned_direct_state=2,
            expected_output=(
                "Deleted 3 objects, deleted 2 state items, and pruned 2 direct state tables.\n"
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
        deleted_state_backups=placeholder_candidates(test_case.deleted_state_backups),
        deleted_checkpoints=placeholder_candidates(test_case.deleted_checkpoints),
        pruned_direct_state=placeholder_candidates(test_case.pruned_direct_state),
    )

    write_janitor_completion(
        invocation=cast(JanitorInvocation, SimpleNamespace(use_color=False)), result=result
    )

    assert capsys.readouterr().out == test_case.expected_output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
