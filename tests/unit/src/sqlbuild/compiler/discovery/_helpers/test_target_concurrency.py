"""Loading and validation of per-target concurrency."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import ProjectConfig, ProjectConfigError
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    TargetConcurrencyConfigTestCase,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers.helpers import load_project_config

_PROJECT: str = 'name = "shop"\nadapter = "duckdb"\n\n[targets.prod]\nschema = "main"\n'


@pytest.mark.parametrize(
    "test_case",
    [
        TargetConcurrencyConfigTestCase(
            description="a positive integer is loaded",
            target_lines="concurrency = 8\n",
            expected_concurrency=8,
        ),
        TargetConcurrencyConfigTestCase(
            description="an absent value leaves the target unset",
            target_lines="",
            expected_concurrency=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_target_concurrency_when_loading_then_it_is_kept(
    test_case: TargetConcurrencyConfigTestCase, tmp_path: Path
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        _PROJECT + test_case.target_lines, encoding="utf-8"
    )

    config: ProjectConfig = load_project_config(project_dir=tmp_path)

    assert config.targets["prod"].concurrency == test_case.expected_concurrency


@pytest.mark.parametrize(
    "test_case",
    [
        TargetConcurrencyConfigTestCase(
            description="zero is rejected",
            target_lines="concurrency = 0\n",
            expected_error_fragment="targets.prod.concurrency must be an integer >= 1",
        ),
        TargetConcurrencyConfigTestCase(
            description="a boolean is rejected",
            target_lines="concurrency = true\n",
            expected_error_fragment="targets.prod.concurrency must be an integer >= 1",
        ),
        TargetConcurrencyConfigTestCase(
            description="a string is rejected",
            target_lines='concurrency = "8"\n',
            expected_error_fragment="targets.prod.concurrency must be an integer >= 1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_target_concurrency_when_loading_then_coded_error_is_raised(
    test_case: TargetConcurrencyConfigTestCase, tmp_path: Path
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        _PROJECT + test_case.target_lines, encoding="utf-8"
    )

    with pytest.raises(ProjectConfigError) as error:
        load_project_config(project_dir=tmp_path)

    assert error.value.code == test_case.expected_error_code
    assert test_case.expected_error_fragment in str(error.value)
