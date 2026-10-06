"""Loading, validation and local precedence of per-target diff limits."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.yml.project import (
    load_local_config,
    load_project_config,
)
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    TargetDiffConfigErrorTestCase,
    TargetDiffConfigTestCase,
)

_PROJECT: str = 'name = "shop"\nadapter = "duckdb"\n\n[targets.dev]\nschema = "dev"\n'


@pytest.mark.parametrize(
    "test_case",
    [
        TargetDiffConfigTestCase(
            description="target without a diff section leaves the limit unset",
            project_contents=_PROJECT,
            expected_max_full_rows=None,
        ),
        TargetDiffConfigTestCase(
            description="positive integer limit is kept",
            project_contents=_PROJECT + "\n[targets.dev.diff]\nmax_full_rows = 25_000\n",
            expected_max_full_rows=25_000,
        ),
        TargetDiffConfigTestCase(
            description="unlimited keyword disables the limit",
            project_contents=_PROJECT + '\n[targets.dev.diff]\nmax_full_rows = "unlimited"\n',
            expected_max_full_rows="unlimited",
        ),
        TargetDiffConfigTestCase(
            description="local limit replaces the project limit",
            project_contents=_PROJECT + "\n[targets.dev.diff]\nmax_full_rows = 25_000\n",
            local_contents="[targets.dev.diff]\nmax_full_rows = 90_000\n",
            expected_max_full_rows=90_000,
        ),
        TargetDiffConfigTestCase(
            description="local unlimited replaces a project integer limit",
            project_contents=_PROJECT + "\n[targets.dev.diff]\nmax_full_rows = 25_000\n",
            local_contents='[targets.dev.diff]\nmax_full_rows = "unlimited"\n',
            expected_max_full_rows="unlimited",
        ),
        TargetDiffConfigTestCase(
            description="local target without a diff section inherits the project limit",
            project_contents=_PROJECT + "\n[targets.dev.diff]\nmax_full_rows = 25_000\n",
            local_contents='[targets.dev]\nschema = "dev_alice"\n',
            expected_max_full_rows=25_000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_diff_section_when_loading_then_effective_limit_follows_local_precedence(
    test_case: TargetDiffConfigTestCase, tmp_path: Path
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.project_contents, encoding="utf-8")
    (tmp_path / "sqlbuild_local.toml").write_text(test_case.local_contents, encoding="utf-8")

    max_full_rows: int | str | None = resolve_target_config(
        project_config=load_project_config(project_dir=tmp_path),
        local_config=load_local_config(project_dir=tmp_path),
        target_name="dev",
    ).diff.max_full_rows

    assert max_full_rows == test_case.expected_max_full_rows


@pytest.mark.parametrize(
    "test_case",
    [
        TargetDiffConfigErrorTestCase(
            description="zero is rejected",
            project_contents=_PROJECT + "\n[targets.dev.diff]\nmax_full_rows = 0\n",
            expected_error_fragment="targets.dev.diff.max_full_rows must be an integer >= 1",
        ),
        TargetDiffConfigErrorTestCase(
            description="negative integer is rejected",
            project_contents=_PROJECT + "\n[targets.dev.diff]\nmax_full_rows = -5\n",
            expected_error_fragment="targets.dev.diff.max_full_rows must be an integer >= 1",
        ),
        TargetDiffConfigErrorTestCase(
            description="boolean is rejected",
            project_contents=_PROJECT + "\n[targets.dev.diff]\nmax_full_rows = true\n",
            expected_error_fragment="targets.dev.diff.max_full_rows must be an integer >= 1",
        ),
        TargetDiffConfigErrorTestCase(
            description="other strings are rejected",
            project_contents=_PROJECT + '\n[targets.dev.diff]\nmax_full_rows = "none"\n',
            expected_error_fragment="or 'unlimited'",
        ),
        TargetDiffConfigErrorTestCase(
            description="float is rejected",
            project_contents=_PROJECT + "\n[targets.dev.diff]\nmax_full_rows = 1.5\n",
            expected_error_fragment="targets.dev.diff.max_full_rows must be an integer >= 1",
        ),
        TargetDiffConfigErrorTestCase(
            description="unknown diff key is rejected",
            project_contents=_PROJECT + "\n[targets.dev.diff]\nmax_rows = 10\n",
            expected_error_fragment="targets.dev.diff has unknown keys: max_rows",
        ),
        TargetDiffConfigErrorTestCase(
            description="invalid local limit is rejected",
            project_contents=_PROJECT,
            local_contents="[targets.dev.diff]\nmax_full_rows = 0\n",
            expected_error_fragment="targets.dev.diff.max_full_rows must be an integer >= 1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_target_diff_section_when_loading_then_config_error_names_key(
    test_case: TargetDiffConfigErrorTestCase, tmp_path: Path
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.project_contents, encoding="utf-8")
    (tmp_path / "sqlbuild_local.toml").write_text(test_case.local_contents, encoding="utf-8")

    with pytest.raises(ProjectConfigError) as error_info:
        load_project_config(project_dir=tmp_path)
        load_local_config(project_dir=tmp_path)

    assert test_case.expected_error_fragment in str(error_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
