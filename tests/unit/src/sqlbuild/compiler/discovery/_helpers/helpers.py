from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
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
    override: str | None = test_case.expected_dbt_production_ref_generate_schema_name_override
    _OVERRIDE_WRITERS[override is not None](tmp_path, override)


def _write_override(tmp_path: Path, override: str | None) -> None:
    macro_file: Path = tmp_path / cast(str, override)
    macro_file.parent.mkdir(parents=True, exist_ok=True)
    macro_file.write_text(
        "{% macro generate_schema_name(custom_schema_name, node) %}dev{% endmacro %}",
        encoding="utf-8",
    )


def _skip_override(tmp_path: Path, override: str | None) -> None:
    del tmp_path, override


_OVERRIDE_WRITERS: MappingProxyType[bool, Callable[[Path, str | None], None]] = MappingProxyType(
    {False: _skip_override, True: _write_override}
)
