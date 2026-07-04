from __future__ import annotations

import re

import pytest

from sqlbuild.compiler.compile.helpers.attachment.core import resolve_run_id
from sqlbuild.compiler.compile.main.effective_runtime import build_effective_runtime_config
from sqlbuild.compiler.compile.main.effective_target import build_effective_target_config
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import (
    LocalConfig,
    LocalTargetConfig,
    ProjectConfig,
    TargetConfig,
)
from tests.unit.src.sqlbuild.compiler.compile._test_types import (
    BuildEffectiveRuntimeConfigTestCase,
    BuildEffectiveTargetConfigTestCase,
    RunIdGenerationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildEffectiveRuntimeConfigTestCase(
            description="uses default target and var precedence",
            selected_target=None,
            cli_vars={"shared": "cli", "cli_only": "cli"},
            expected_target_name="dev",
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
            description="selected target overrides local target",
            selected_target="prod",
            cli_vars=None,
            expected_target_name="prod",
            expected_vars={
                "shared": "local",
                "project_only": "project",
                "environment_only": "prod",
                "local_only": "local",
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_config_inputs_when_building_effective_runtime_then_returns_expected_values(
    test_case: BuildEffectiveRuntimeConfigTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            default_target="dev",
            vars={"shared": "project", "project_only": "project"},
            targets={
                "dev": TargetConfig(
                    vars={"shared": "dev", "environment_only": "dev"},
                ),
                "prod": TargetConfig(
                    vars={"shared": "prod", "environment_only": "prod"},
                ),
            },
        ),
        local_config=LocalConfig(
            target="dev",
            vars={"shared": "local", "local_only": "local"},
            targets={
                "dev": LocalTargetConfig(
                    vars={"shared": "local_dev", "local_environment_only": "local_dev"},
                ),
            },
        ),
    )

    target_name: str | None
    effective_vars: dict[str, object]
    run_id: str
    target_name, effective_vars, run_id = build_effective_runtime_config(
        discovered_inputs=discovered_inputs,
        selected_target=test_case.selected_target,
        cli_vars=test_case.cli_vars,
    )

    assert target_name == test_case.expected_target_name
    assert effective_vars == test_case.expected_vars
    assert re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", run_id)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildEffectiveTargetConfigTestCase(
            description="exposes resolved target reuse metadata",
            selected_target=None,
            expected_reuse_from="prod",
            expected_reuse_hard_copy=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_config_inputs_when_building_effective_target_then_exposes_reuse_metadata(
    test_case: BuildEffectiveTargetConfigTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            default_target="dev",
            targets={
                "dev": TargetConfig(reuse_from="staging", reuse_hard_copy=False),
                "prod": TargetConfig(),
            },
        ),
        local_config=LocalConfig(
            targets={
                "dev": LocalTargetConfig(reuse_from="prod", reuse_hard_copy=True),
            }
        ),
    )

    target_config: TargetConfig | None = build_effective_target_config(
        discovered_inputs=discovered_inputs,
        selected_target=test_case.selected_target,
    )

    assert target_config is not None
    assert target_config.reuse_from == test_case.expected_reuse_from
    assert target_config.reuse_hard_copy is test_case.expected_reuse_hard_copy


@pytest.mark.parametrize(
    "test_case",
    [
        RunIdGenerationTestCase(
            description="generated run ids use twelve hex suffixes and are unique",
            sample_count=100,
            expected_pattern=r"\d{8}T\d{6}Z_[0-9a-f]{12}",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_run_ids_when_resolving_then_uses_expected_shape_and_unique_suffixes(
    test_case: RunIdGenerationTestCase,
) -> None:
    run_ids: tuple[str, ...] = tuple(
        resolve_run_id(selected_run_id=None) for _ in range(test_case.sample_count)
    )

    assert len(set(run_ids)) == len(run_ids)
    assert all(re.fullmatch(test_case.expected_pattern, run_id) for run_id in run_ids)
