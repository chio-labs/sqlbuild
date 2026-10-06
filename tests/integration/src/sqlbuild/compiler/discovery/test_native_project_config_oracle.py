"""Compare the native project configuration reader with SQLBuild's Python loaders."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    RepositoryFileOracleTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    deferred_valid_count,
    harmful_mismatches,
    native_project_outcome,
    python_project_outcome,
    repository_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RepositoryFileOracleTestCase(
            description="fixture and example projects",
            pattern="**/sqlbuild_project.toml",
            expected_minimum_files=5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repository_projects_when_reading_natively_then_discovery_fields_match_python(
    test_case: RepositoryFileOracleTestCase,
) -> None:
    project_dirs: list[Path] = [path.parent for path in repository_files(pattern=test_case.pattern)]

    expected: list[object] = [python_project_outcome(project_dir=path) for path in project_dirs]
    actual: list[object] = [native_project_outcome(project_dir=path) for path in project_dirs]

    assert len(project_dirs) >= test_case.expected_minimum_files
    assert deferred_valid_count(expected=expected, actual=actual) == test_case.expected_deferred
    assert harmful_mismatches(
        inputs=list(map(str, project_dirs)), expected=expected, actual=actual
    ) == list(test_case.expected_mismatches)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
