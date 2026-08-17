from pathlib import Path
from typing import cast

from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    LoadProjectConfigTestCase,
)


def expected_or_actual[T](expected: T | None, actual: T) -> T:
    return (actual, cast(T, expected))[expected is not None]


def write_project_config_test_files(
    *, tmp_path: Path, test_case: LoadProjectConfigTestCase
) -> None:
    project_file: Path = tmp_path / "sqlbuild_project.toml"
    project_file.write_text(test_case.project_file_contents, encoding="utf-8")
