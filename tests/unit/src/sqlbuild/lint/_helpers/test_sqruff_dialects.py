"""Unit tests for sqruff dialect validation before invocation."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.lint._helpers.sqruff_engine import run_sqruff_lint
from sqlbuild.lint.exceptions import UnsupportedDialectError
from sqlbuild.lint.models import LintConfig, LintViolation
from tests.unit.src.sqlbuild.lint._helpers._test_types import (
    SupportedDialectTestCase,
    UnsupportedDialectTestCase,
)
from tests.unit.src.sqlbuild.lint._helpers.helpers import lint_bodies_for

CLEAN_BODY: str = "SELECT 1 AS x\n"


@pytest.mark.parametrize(
    "test_case",
    [
        UnsupportedDialectTestCase(
            description="misspelled dialect is rejected instead of silently defaulting",
            sqruff_config='[core]\ndialect = "duckdbb"\n',
            expected_message_fragments=("duckdbb", "does not support", "duckdb"),
        ),
        UnsupportedDialectTestCase(
            description="dialect from another tool is rejected",
            sqruff_config='[core]\ndialect = "spark"\n',
            expected_message_fragments=("spark", "Supported dialects"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_dialect_when_linting_then_error_is_raised(
    test_case: UnsupportedDialectTestCase, tmp_path: Path
) -> None:
    _ = (tmp_path / ".sqruff").write_text(test_case.sqruff_config, encoding="utf-8")
    body_path: Path = tmp_path / "model.sql"
    config: LintConfig = LintConfig(sqruff_enabled=True, sqruff_config_path=".sqruff")
    with pytest.raises(UnsupportedDialectError) as error:
        _ = run_sqruff_lint(
            bodies=lint_bodies_for(file_path=body_path, contents=CLEAN_BODY),
            contents_by_path={body_path: CLEAN_BODY},
            config=config,
            project_dir=tmp_path,
        )
    fragment: str
    for fragment in test_case.expected_message_fragments:
        assert fragment in str(error.value)


@pytest.mark.parametrize(
    "test_case",
    [
        SupportedDialectTestCase(
            description="supported dialect lints without error",
            sqruff_config='[core]\ndialect = "duckdb"\n',
            expected_violation_count=0,
        ),
        SupportedDialectTestCase(
            description="config without a dialect lints without error",
            sqruff_config='[core]\nrules = "LT02"\n',
            expected_violation_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_dialect_when_linting_then_run_completes(
    test_case: SupportedDialectTestCase, tmp_path: Path
) -> None:
    _ = (tmp_path / ".sqruff").write_text(test_case.sqruff_config, encoding="utf-8")
    body_path: Path = tmp_path / "model.sql"
    config: LintConfig = LintConfig(sqruff_enabled=True, sqruff_config_path=".sqruff")
    violations: dict[Path, tuple[LintViolation, ...]] = run_sqruff_lint(
        bodies=lint_bodies_for(file_path=body_path, contents=CLEAN_BODY),
        contents_by_path={body_path: CLEAN_BODY},
        config=config,
        project_dir=tmp_path,
    )
    assert len(violations[body_path]) == test_case.expected_violation_count
