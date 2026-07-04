from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError
from sqlbuild.integrations.dbt.helpers.config.core import resolve_dbt_config
from sqlbuild.integrations.dbt.helpers.planning.runtime import resolve_dbt_vars
from sqlbuild.integrations.dbt.models import ResolvedDbtConfig
from sqlbuild.spec.models.project import DbtConfig, LocalDbtConfig
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtConfigErrorTestCase,
    DbtConfigResolutionTestCase,
    DbtVarsResolutionTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import build_cli_overrides


@pytest.mark.parametrize(
    "test_case",
    [
        DbtConfigResolutionTestCase(
            description="uses project config when cli values are absent",
            config=DbtConfig(
                project_dir="dbt",
                profiles_dir="profiles",
                target="dev",
                target_path="target/dbt",
            ),
            cli_project_dir=None,
            cli_profiles_dir=None,
            cli_target=None,
            cli_target_path=None,
            require_project_dir=True,
            expected_project_dir=Path("/repo/dbt"),
            expected_profiles_dir=Path("/repo/profiles"),
            expected_target="dev",
            expected_target_path=Path("/repo/target/dbt"),
        ),
        DbtConfigResolutionTestCase(
            description="cli values override project config",
            config=DbtConfig(
                project_dir="dbt",
                profiles_dir="profiles",
                target="dev",
                target_path="target/dbt",
            ),
            cli_project_dir="../analytics",
            cli_profiles_dir="../profiles",
            cli_target="prod",
            cli_target_path="../dbt-target",
            require_project_dir=True,
            expected_project_dir=Path("/analytics"),
            expected_profiles_dir=Path("/profiles"),
            expected_target="prod",
            expected_target_path=Path("/dbt-target"),
        ),
        DbtConfigResolutionTestCase(
            description="local target overrides project target when cli target is absent",
            config=DbtConfig(
                project_dir="dbt",
                target="dev",
            ),
            local_config=LocalDbtConfig(target="pat"),
            cli_project_dir=None,
            cli_profiles_dir=None,
            cli_target=None,
            cli_target_path=None,
            require_project_dir=True,
            expected_project_dir=Path("/repo/dbt"),
            expected_profiles_dir=None,
            expected_target="pat",
            expected_target_path=None,
        ),
        DbtConfigResolutionTestCase(
            description="normal sqb commands can omit project dir when dbt is not required",
            config=DbtConfig(),
            cli_project_dir=None,
            cli_profiles_dir=None,
            cli_target=None,
            cli_target_path=None,
            require_project_dir=False,
            expected_project_dir=None,
            expected_profiles_dir=None,
            expected_target=None,
            expected_target_path=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_config_when_resolving_then_returns_expected_values(
    test_case: DbtConfigResolutionTestCase,
) -> None:
    result: ResolvedDbtConfig = resolve_dbt_config(
        project_root=Path("/repo"),
        config=test_case.config,
        overrides=build_cli_overrides(
            project_dir=test_case.cli_project_dir,
            profiles_dir=test_case.cli_profiles_dir,
            target=test_case.cli_target,
            target_path=test_case.cli_target_path,
        ),
        require_project_dir=test_case.require_project_dir,
        local_config=test_case.local_config,
    )

    assert result.project_dir == test_case.expected_project_dir
    assert result.profiles_dir == test_case.expected_profiles_dir
    assert result.target == test_case.expected_target
    assert result.target_path == test_case.expected_target_path


@pytest.mark.parametrize(
    "test_case",
    [
        DbtVarsResolutionTestCase(
            description="merges project local and cli vars with later values winning",
            project_config=DbtConfig(
                vars={"country": "US", "limit": 100, "shared": "project"},
            ),
            local_config=LocalDbtConfig(vars={"limit": 10, "developer": "kevin"}),
            dbt_args=("--vars", '{"country": "CA", "cli_only": true}'),
            expected_vars={
                "country": "CA",
                "limit": 10,
                "shared": "project",
                "developer": "kevin",
                "cli_only": True,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_vars_sources_when_resolving_then_vars_are_merged(
    test_case: DbtVarsResolutionTestCase,
) -> None:
    resolved: str | None = resolve_dbt_vars(
        project_config=test_case.project_config,
        local_config=test_case.local_config,
        dbt_args=test_case.dbt_args,
    )

    assert resolved is not None
    assert json.loads(resolved) == test_case.expected_vars


@pytest.mark.parametrize(
    "test_case",
    [
        DbtConfigErrorTestCase(
            description="requires project dir when dbt interop command needs dbt",
            config=DbtConfig(),
            cli_project_dir=None,
            expected_error_fragment="dbt project directory is not configured",
            expected_code="C240",
            expected_help_fragment="Add [dbt].project_dir",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_required_dbt_project_when_resolving_then_raises_value_error(
    test_case: DbtConfigErrorTestCase,
) -> None:
    with pytest.raises(DbtInteropConfigError, match=test_case.expected_error_fragment) as captured:
        resolve_dbt_config(
            project_root=Path("/repo"),
            config=test_case.config,
            overrides=build_cli_overrides(project_dir=test_case.cli_project_dir),
            require_project_dir=True,
        )

    assert captured.value.code == test_case.expected_code
    assert captured.value.help is not None
    assert test_case.expected_help_fragment in captured.value.help
