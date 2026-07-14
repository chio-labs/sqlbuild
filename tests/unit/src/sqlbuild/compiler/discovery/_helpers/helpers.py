from pathlib import Path

from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    LoadProjectConfigTestCase,
)


def expected_or_actual[T](expected: T | None, actual: T) -> T:
    if expected is None:
        return actual
    return expected


def write_project_config_test_files(
    *, tmp_path: Path, test_case: LoadProjectConfigTestCase
) -> None:
    project_file: Path = tmp_path / "sqlbuild_project.toml"
    project_file.write_text(test_case.project_file_contents, encoding="utf-8")
    if test_case.expected_dbt_production_ref_generate_schema_name_override is None:
        return

    macro_file: Path = (
        tmp_path / test_case.expected_dbt_production_ref_generate_schema_name_override
    )
    macro_file.parent.mkdir(parents=True, exist_ok=True)
    macro_file.write_text(
        "{% macro generate_schema_name(custom_schema_name, node) %}dev{% endmacro %}",
        encoding="utf-8",
    )
