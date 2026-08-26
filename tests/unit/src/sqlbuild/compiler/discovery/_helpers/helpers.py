from collections.abc import Callable
from pathlib import Path
from typing import cast

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_constant_files,
    discover_enum_files,
    discover_macro_files,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredMacroFile,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    LoadProjectConfigTestCase,
)

_DECLARATION_CONTENTS_BY_KIND: dict[str, tuple[str, str]] = {
    "macro": (".py", "def scoped_value():\n    return 1\n"),
    "enum": (".sql", "ENUM (name scoped_value, members [ONE, TWO]);\n"),
    "constant": (".sql", "CONSTANT (name scoped_value, value 1);\n"),
}
_DECLARATION_DISCOVERER_BY_KIND: dict[
    str,
    Callable[
        ...,
        tuple[DiscoveredMacroFile | DiscoveredEnumFile | DiscoveredConstantFile, ...],
    ],
] = {
    "macro": discover_macro_files,
    "enum": discover_enum_files,
    "constant": discover_constant_files,
}


def expected_or_actual[T](expected: T | None, actual: T) -> T:
    return (actual, cast(T, expected))[expected is not None]


def write_project_config_test_files(
    *, tmp_path: Path, test_case: LoadProjectConfigTestCase
) -> None:
    project_file: Path = tmp_path / "sqlbuild_project.toml"
    project_file.write_text(test_case.project_file_contents, encoding="utf-8")


def declaration_contents(*, kind: str) -> tuple[str, str]:
    return _DECLARATION_CONTENTS_BY_KIND[kind]


def discover_declarations(
    *, project_dir: Path, kind: str
) -> tuple[DiscoveredMacroFile | DiscoveredEnumFile | DiscoveredConstantFile, ...]:
    return _DECLARATION_DISCOVERER_BY_KIND[kind](project_dir=project_dir)
