"""Only the facts module of `sqb rename` and `sqb mv` reads `CompiledProject`."""

from __future__ import annotations

from pathlib import Path

import pytest

import sqlbuild.cli.commands._helpers.refactor as refactor_package
from tests.unit.src.sqlbuild.cli.commands._helpers.refactor._test_types import (
    ImportBoundaryTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.refactor.helpers import modules_importing


@pytest.mark.parametrize(
    "test_case",
    [
        ImportBoundaryTestCase(
            description="the native command core will return these facts instead",
            imported_name="CompiledProject",
            expected_modules=("facts.py",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_refactor_shell_when_reading_imports_then_only_facts_module_reads_compiled_project(
    test_case: ImportBoundaryTestCase,
) -> None:
    package_dir: Path = Path(refactor_package.__file__).parent

    importing: list[str] = modules_importing(package_dir=package_dir, name=test_case.imported_name)

    assert tuple(importing) == test_case.expected_modules


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
