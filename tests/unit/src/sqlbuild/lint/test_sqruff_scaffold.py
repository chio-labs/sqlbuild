"""Unit tests for sqruff config scaffolding and dialect translation."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.lint._helpers.sqruff_scaffold import translate_adapter_dialect
from sqlbuild.lint.main.ensure_config import ensure_sqruff_config
from tests.unit.src.sqlbuild.lint._test_types import (
    SqruffScaffoldCreateTestCase,
    SqruffScaffoldDisabledTestCase,
    SqruffScaffoldExistingTestCase,
    TranslateDialectTestCase,
)

PROJECT_TOML_TEMPLATE: str = 'name = "demo"\nadapter = "{adapter}"\n'
DRIFT_WARNING_TEMPLATE: str = (
    ".sqruff dialect '{configured}' differs from project adapter "
    "'{adapter}' ('{translated}'); using .sqruff as-is"
)


@pytest.mark.parametrize(
    "test_case",
    [
        TranslateDialectTestCase(
            description="duckdb maps to duckdb",
            adapter="duckdb",
            expected_dialect="duckdb",
        ),
        TranslateDialectTestCase(
            description="motherduck maps to duckdb",
            adapter="motherduck",
            expected_dialect="duckdb",
        ),
        TranslateDialectTestCase(
            description="sqlserver maps to tsql",
            adapter="sqlserver",
            expected_dialect="tsql",
        ),
        TranslateDialectTestCase(
            description="postgres maps identically",
            adapter="postgres",
            expected_dialect="postgres",
        ),
        TranslateDialectTestCase(
            description="unknown adapters have no translation",
            adapter="futuresparks",
            expected_dialect=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_when_translating_then_dialect_matches_expected(
    test_case: TranslateDialectTestCase,
) -> None:
    dialect: str | None = translate_adapter_dialect(adapter=test_case.adapter)
    assert dialect == test_case.expected_dialect


@pytest.mark.parametrize(
    "test_case",
    [
        SqruffScaffoldCreateTestCase(
            description="missing config is scaffolded with the translated dialect",
            project_adapter="duckdb",
            expected_final_config='[core]\ndialect = "duckdb"\n',
        ),
        SqruffScaffoldCreateTestCase(
            description="missing config for sqlserver is scaffolded as tsql",
            project_adapter="sqlserver",
            expected_final_config='[core]\ndialect = "tsql"\n',
        ),
        SqruffScaffoldCreateTestCase(
            description="untranslatable adapter is scaffolded as ansi",
            project_adapter="futuresparks",
            expected_final_config='[core]\ndialect = "ansi"\n',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_config_when_ensuring_then_dialect_is_scaffolded(
    test_case: SqruffScaffoldCreateTestCase, tmp_path: Path
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        PROJECT_TOML_TEMPLATE.format(adapter=test_case.project_adapter), encoding="utf-8"
    )
    warning: str | None = ensure_sqruff_config(
        project_dir=tmp_path, config_path=".sqruff", sqruff_enabled=True
    )
    assert warning is None
    written: str = (tmp_path / ".sqruff").read_text(encoding="utf-8")
    assert written == test_case.expected_final_config


@pytest.mark.parametrize(
    "test_case",
    [
        SqruffScaffoldExistingTestCase(
            description="existing config with matching dialect is untouched",
            project_adapter="snowflake",
            existing_config='[core]\ndialect = "snowflake"\n',
            expected_warning=None,
        ),
        SqruffScaffoldExistingTestCase(
            description="existing config with drifting dialect warns and stays as-is",
            project_adapter="snowflake",
            existing_config='[core]\ndialect = "postgres"\n',
            expected_warning=DRIFT_WARNING_TEMPLATE.format(
                configured="postgres", adapter="snowflake", translated="snowflake"
            ),
        ),
        SqruffScaffoldExistingTestCase(
            description="existing config without a dialect never warns",
            project_adapter="bigquery",
            existing_config='[core]\nrules = "LT02"\n',
            expected_warning=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_config_when_ensuring_then_file_is_preserved(
    test_case: SqruffScaffoldExistingTestCase, tmp_path: Path
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        PROJECT_TOML_TEMPLATE.format(adapter=test_case.project_adapter), encoding="utf-8"
    )
    config_file: Path = tmp_path / ".sqruff"
    _ = config_file.write_text(test_case.existing_config, encoding="utf-8")
    warning: str | None = ensure_sqruff_config(
        project_dir=tmp_path, config_path=".sqruff", sqruff_enabled=True
    )
    assert warning == test_case.expected_warning
    assert config_file.read_text(encoding="utf-8") == test_case.existing_config


@pytest.mark.parametrize(
    "test_case",
    [
        SqruffScaffoldDisabledTestCase(
            description="disabled sqruff never creates a config",
            project_adapter="duckdb",
            expected_config_exists=False,
            expected_warning=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_disabled_sqruff_when_ensuring_then_no_config_is_written(
    test_case: SqruffScaffoldDisabledTestCase, tmp_path: Path
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        PROJECT_TOML_TEMPLATE.format(adapter=test_case.project_adapter), encoding="utf-8"
    )
    warning: str | None = ensure_sqruff_config(
        project_dir=tmp_path, config_path=".sqruff", sqruff_enabled=False
    )
    assert warning == test_case.expected_warning
    assert (tmp_path / ".sqruff").exists() == test_case.expected_config_exists
