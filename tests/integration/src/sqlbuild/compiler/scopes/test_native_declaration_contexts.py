"""Native declaration resolution contexts match Python's for every consumer of a project."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.helpers import mismatches
from tests.integration.src.sqlbuild.compiler.scopes._test_types import (
    DeclarationContextParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.scopes.helpers import (
    SCOPED_PROJECT,
    ContextParity,
    combined_context_parity,
    declaration_context_parity,
    generated_scope_files,
    write_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationContextParityTestCase(
            description="seeded scoped projects with grants, private and folder-scoped values",
            seed=20261007,
            count=60,
            expected_minimum_native=250,
            expected_minimum_granted=40,
            expected_minimum_private=50,
            expected_minimum_python_only=60,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_projects_when_resolving_contexts_natively_then_python_contexts_match(
    test_case: DeclarationContextParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    project_dirs: list[Path] = [tmp_path / "scoped"] + [
        tmp_path / f"project_{index}" for index in range(test_case.count)
    ]
    write_project(project_dir=project_dirs[0], files=SCOPED_PROJECT)
    for project_dir in project_dirs[1:]:
        write_project(project_dir=project_dir, files=generated_scope_files(rng=rng))

    parity: ContextParity = combined_context_parity(
        [
            declaration_context_parity(project_dir=project_dir, monkeypatch=monkeypatch)
            for project_dir in project_dirs
        ]
    )

    assert (
        mismatches(inputs=[*parity.targets], expected=[*parity.python], actual=[*parity.native]),
        parity.native_contexts >= test_case.expected_minimum_native,
        parity.granted_contexts >= test_case.expected_minimum_granted,
        parity.private_contexts >= test_case.expected_minimum_private,
        parity.python_only_paths >= test_case.expected_minimum_python_only,
    ) == ([], True, True, True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
