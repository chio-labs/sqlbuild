from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.integrations.dbt.helpers.profile.init import build_dbt_init_project
from sqlbuild.integrations.dbt.models import DbtInitRequest, DbtInitResult
from tests.unit.src.sqlbuild.integrations.dbt.profile._test_types import (
    DbtProfileInitDiscoveryTestCase,
    DbtProfileInitTomlTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileInitTomlTestCase(
            description="generated TOML references dbt profile without materializing secret path",
            secret_value="/tmp/secret-profile.duckdb",
            expected_fragments=(
                'adapter = "duckdb"',
                'source = "dbt_profile"',
                'profile = "analytics"',
                'target = "dev"',
                "[dbt.production_ref]",
                'git_ref = "main"',
                'generate_schema_name_override = "dbt/macros/generate_schema_name.sql"',
                "[targets.dev]",
                'schema = "main"',
            ),
            unexpected_fragments=("/tmp/secret-profile.duckdb",),
        )
    ],
    ids=["generated TOML references dbt profile without materializing secret path"],
)
def test_given_dbt_duckdb_profile_when_building_init_project_then_toml_omits_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: DbtProfileInitTomlTestCase,
) -> None:
    dbt_project_dir: Path = tmp_path / "dbt_project"
    profiles_dir: Path = tmp_path / "profiles"
    dbt_project_dir.mkdir()
    profiles_dir.mkdir()
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics_project\nprofile: analytics\ntarget-path: target\n",
        encoding="utf-8",
    )
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        "      path: \"{{ env_var('DBT_SECRET_DUCKDB_PATH') }}\"\n"
        "      schema: main\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DBT_SECRET_DUCKDB_PATH", test_case.secret_value)

    result: DbtInitResult = build_dbt_init_project(
        request=DbtInitRequest(
            cwd=tmp_path,
            dbt_project_dir=Path("dbt_project"),
            profiles_dir=Path("profiles"),
            profile_name=None,
            target_name=None,
            sqb_output_dir=Path("sqlbuild_project"),
            dry_run=False,
            overwrite=False,
            skip_dbt_debug=True,
        )
    )

    assert result.project_file.exists()
    assert result.macro_file.exists()
    macro_text: str = result.macro_file.read_text(encoding="utf-8")
    assert "macro generate_schema_name" in macro_text
    assert "{{ custom_schema_name | trim }}" in macro_text
    assert "{{ target.schema }}_{{ custom_schema_name | trim }}" not in macro_text
    for fragment in test_case.expected_fragments:
        assert fragment in result.toml
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result.toml


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileInitDiscoveryTestCase(
            description="uses project-local profiles file when profiles dir is omitted",
            expected_profiles_dir_fragment='profiles_dir = "../dbt_project"',
        )
    ],
    ids=["uses project-local profiles file when profiles dir is omitted"],
)
def test_given_project_local_profiles_when_building_init_project_then_profiles_dir_is_discovered(
    tmp_path: Path,
    test_case: DbtProfileInitDiscoveryTestCase,
) -> None:
    dbt_project_dir: Path = tmp_path / "dbt_project"
    dbt_project_dir.mkdir()
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics_project\nprofile: analytics\ntarget-path: target\n",
        encoding="utf-8",
    )
    (dbt_project_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        "      path: local.duckdb\n"
        "      schema: main\n",
        encoding="utf-8",
    )

    result: DbtInitResult = build_dbt_init_project(
        request=DbtInitRequest(
            cwd=dbt_project_dir,
            dbt_project_dir=Path("."),
            profiles_dir=None,
            profile_name=None,
            target_name=None,
            sqb_output_dir=Path("../sqlbuild_project"),
            dry_run=True,
            overwrite=False,
            skip_dbt_debug=True,
        )
    )

    assert test_case.expected_profiles_dir_fragment in result.toml
