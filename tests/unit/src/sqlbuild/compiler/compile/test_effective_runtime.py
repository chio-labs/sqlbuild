from __future__ import annotations

import re

import pytest

from sqlbuild.compiler.compile.main.effective_runtime import build_effective_runtime_config
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import (
    EnvironmentConfig,
    LocalConfig,
    LocalEnvironmentConfig,
    ProjectConfig,
)
from tests.unit.src.sqlbuild.compiler.compile._test_types import (
    BuildEffectiveRuntimeConfigTestCase,
)

RUNTIME_CONFIG_TEST_CASES: list[BuildEffectiveRuntimeConfigTestCase] = [
    BuildEffectiveRuntimeConfigTestCase(
        description="uses default environment and var precedence",
        selected_environment=None,
        cli_vars={"shared": "cli", "cli_only": "cli"},
        expected_environment_name="dev",
        expected_vars={
            "shared": "cli",
            "project_only": "project",
            "environment_only": "dev",
            "local_only": "local",
            "local_environment_only": "local_dev",
            "cli_only": "cli",
        },
    ),
    BuildEffectiveRuntimeConfigTestCase(
        description="selected environment overrides local environment",
        selected_environment="prod",
        cli_vars=None,
        expected_environment_name="prod",
        expected_vars={
            "shared": "local",
            "project_only": "project",
            "environment_only": "prod",
            "local_only": "local",
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RUNTIME_CONFIG_TEST_CASES,
    ids=[case.description for case in RUNTIME_CONFIG_TEST_CASES],
)
def test_given_runtime_config_inputs_when_building_effective_runtime_then_returns_expected_values(
    test_case: BuildEffectiveRuntimeConfigTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            default_environment="dev",
            vars={"shared": "project", "project_only": "project"},
            environments={
                "dev": EnvironmentConfig(
                    vars={"shared": "dev", "environment_only": "dev"},
                ),
                "prod": EnvironmentConfig(
                    vars={"shared": "prod", "environment_only": "prod"},
                ),
            },
        ),
        local_config=LocalConfig(
            environment="dev",
            vars={"shared": "local", "local_only": "local"},
            environments={
                "dev": LocalEnvironmentConfig(
                    vars={"shared": "local_dev", "local_environment_only": "local_dev"},
                ),
            },
        ),
    )

    environment_name: str | None
    effective_vars: dict[str, object]
    run_id: str
    environment_name, effective_vars, run_id = build_effective_runtime_config(
        discovered_inputs=discovered_inputs,
        selected_environment=test_case.selected_environment,
        cli_vars=test_case.cli_vars,
    )

    assert environment_name == test_case.expected_environment_name
    assert effective_vars == test_case.expected_vars
    assert re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{6}", run_id)
