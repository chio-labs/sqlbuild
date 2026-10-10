"""Native explicit-reference checks report Python's recorded diagnostics, order and errors."""

from __future__ import annotations

from itertools import chain
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.explicit_references._test_types import (
    ExplicitReferenceGoldenTestCase,
)
from tests.integration.src.sqlbuild.compiler.explicit_references.helpers import (
    EXPLICIT_REFERENCE_PROJECTS,
    compile_outcome,
    outcome_codes,
    write_project,
)
from tests.integration.src.sqlbuild.compiler.helpers import (
    GoldenEntry,
    golden_differences,
    golden_entry,
    golden_name,
    read_golden,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExplicitReferenceGoldenTestCase(
            description="edge projects",
            projects=EXPLICIT_REFERENCE_PROJECTS,
            expected_codes=frozenset({"P005", "P007", "P008"}),
            expected_raised=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reference_edge_projects_when_compiling_then_matches_python_golden(
    test_case: ExplicitReferenceGoldenTestCase, tmp_path: Path
) -> None:
    project_dirs: list[Path] = [
        tmp_path / f"project_{index}" for index in range(len(test_case.projects))
    ]
    _ = [
        write_project(project_dir=project_dir, files=files, toml=toml)
        for project_dir, (_, files, toml) in zip(project_dirs, test_case.projects, strict=True)
    ]
    outcomes: list[tuple[object, ...]] = [
        compile_outcome(project_dir=project_dir) for project_dir in project_dirs
    ]
    golden: list[GoldenEntry] = [
        golden_entry("explicit_references", outcome, masked=(str(project_dir),))
        for project_dir, outcome in zip(project_dirs, outcomes, strict=True)
    ]
    codes: frozenset[object] = frozenset(chain.from_iterable(map(outcome_codes, outcomes)))

    assert (
        golden_differences(
            read_golden(golden_name("explicit_references", test_case.description)), golden
        ),
        test_case.expected_codes <= codes,
        sum(outcome[0] == "error" for outcome in outcomes),
    ) == ([], True, test_case.expected_raised)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
