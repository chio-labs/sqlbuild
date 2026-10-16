"""Project Python always loads from current source, never from stale cached bytecode."""

from pathlib import Path

import pytest

from tests.unit.src.sqlbuild.runtime.user_code.main._test_types import StaleBytecodeTestCase
from tests.unit.src.sqlbuild.runtime.user_code.main.helpers import (
    edit_keeping_size_and_mtime,
    load_rule_limit,
    write_project_with_cached_bytecode,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StaleBytecodeTestCase(
            description="file loaded directly", edited_file="rules/naming.py", expected_value="80"
        ),
        StaleBytecodeTestCase(
            description="module imported by name",
            edited_file="rules/limits.py",
            expected_value="10",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_same_size_edit_with_cached_bytecode_when_loading_then_current_source_runs(
    test_case: StaleBytecodeTestCase, tmp_path: Path
) -> None:
    write_project_with_cached_bytecode(root=tmp_path)
    replacements: dict[str, tuple[str, str]] = {
        "rules/naming.py": ("MAX_NAME_LENGTH * 1", "MAX_NAME_LENGTH * 2"),
        "rules/limits.py": ("= 40", "= 10"),
    }
    old, new = replacements[test_case.edited_file]
    edit_keeping_size_and_mtime(
        root=tmp_path, relative_path=test_case.edited_file, old=old, new=new
    )

    assert load_rule_limit(root=tmp_path) == test_case.expected_value


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
