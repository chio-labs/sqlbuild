from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.integrations.dbt._helpers.profile.render import render_selected_dbt_profile_output
from sqlbuild.integrations.dbt.models import ResolvedDbtProfileOutput, SelectedDbtProfileOutput
from tests.unit.src.sqlbuild.integrations.dbt.profile._test_types import (
    DbtProfileRenderErrorTestCase,
    DbtProfileRenderTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileRenderTestCase(
            description="renders env vars and preserves native numeric filter values",
            output={
                "type": "duckdb",
                "path": "{{ env_var('DBT_DUCKDB_PATH') }}",
                "threads": "{{ env_var('DBT_THREADS', '2') | as_number }}",
            },
            env={"DBT_DUCKDB_PATH": "/tmp/example.duckdb"},
            expected_output={"type": "duckdb", "path": "/tmp/example.duckdb", "threads": 2},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selected_dbt_output_when_rendering_then_returns_expected_native_values(
    test_case: DbtProfileRenderTestCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for key, value in test_case.env.items():
        monkeypatch.setenv(key, value)
    selected: SelectedDbtProfileOutput = SelectedDbtProfileOutput(
        profile_name="analytics",
        target_name="dev",
        output=test_case.output,
    )

    resolved: ResolvedDbtProfileOutput = render_selected_dbt_profile_output(
        selected=selected,
        project_dir=tmp_path / "dbt_project",
        profiles_dir=tmp_path / "profiles",
    )

    assert resolved.output == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileRenderErrorTestCase(
            description="missing env var raises clear error",
            output={"type": "duckdb", "path": "{{ env_var('MISSING_DUCKDB_PATH') }}"},
            expected_error_fragment="MISSING_DUCKDB_PATH",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_env_var_when_rendering_then_raises_clear_error(
    tmp_path: Path,
    test_case: DbtProfileRenderErrorTestCase,
) -> None:
    selected: SelectedDbtProfileOutput = SelectedDbtProfileOutput(
        profile_name="analytics",
        target_name="dev",
        output=test_case.output,
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        render_selected_dbt_profile_output(
            selected=selected,
            project_dir=tmp_path / "dbt_project",
            profiles_dir=tmp_path / "profiles",
        )
