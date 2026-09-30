"""Tests for committing verified refactoring edits into a project."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.refactoring._helpers.project.workspace import commit_changes
from sqlbuild.compiler.refactoring.exceptions import RefactorWriteError
from sqlbuild.compiler.refactoring.models import FileChange
from tests.unit.src.sqlbuild.compiler.refactoring._helpers._test_types import (
    CommitChangesTestCase,
)
from tests.unit.src.sqlbuild.compiler.refactoring._helpers.helpers import (
    read_tree,
    span_edits,
    write_tree,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CommitChangesTestCase(
            description="a failed write restores every file",
            files={"a.sql": "SELECT amount", "m.sql": "SELECT 1"},
            current_files={},
            locked_directory="locked",
            spans=((7, 13, "revenue"),),
            edited_path="a.sql",
            moved_from="m.sql",
            moved_to="locked/m.sql",
            expected_error=PermissionError,
            expected_files={"a.sql": "SELECT amount", "m.sql": "SELECT 1"},
        ),
        CommitChangesTestCase(
            description="a file edited since planning stops the write",
            files={"a.sql": "SELECT amount", "m.sql": "SELECT 1"},
            current_files={"a.sql": "SELECT amount, 2"},
            locked_directory="open",
            spans=((7, 13, "revenue"),),
            edited_path="a.sql",
            moved_from="m.sql",
            moved_to="open/m.sql",
            expected_error=RefactorWriteError,
            expected_files={"a.sql": "SELECT amount, 2", "m.sql": "SELECT 1"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_commit_when_writing_then_project_is_unchanged(
    tmp_path: Path, test_case: CommitChangesTestCase
) -> None:
    write_tree(root=tmp_path, files={**test_case.files, **test_case.current_files})
    (tmp_path / test_case.locked_directory).mkdir()
    (tmp_path / "locked").mkdir(exist_ok=True)
    (tmp_path / "locked").chmod(0o500)
    changes: tuple[FileChange, ...] = (
        FileChange(
            path=test_case.edited_path,
            original_path=test_case.edited_path,
            edits=span_edits(text=test_case.files[test_case.edited_path], spans=test_case.spans),
        ),
        FileChange(path=test_case.moved_to, original_path=test_case.moved_from),
    )

    with pytest.raises(test_case.expected_error):
        _ = commit_changes(project_dir=tmp_path, originals=test_case.files, changes=changes)
    (tmp_path / "locked").chmod(0o700)

    assert read_tree(root=tmp_path) == test_case.expected_files


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
