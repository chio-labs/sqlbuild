"""Scenario run namespace configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import (
    ProjectConfigError,
    discover_project_inputs,
    resolve_effective_scenario_config,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.spec.contracts.main._test_types import (
    InvalidScenarioNamespaceConfigTestCase,
    ScenarioNamespaceConfigTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        ScenarioNamespaceConfigTestCase(
            "both config files", project="project", local="local", expected_value="local"
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_project_and_local_config_when_discovering_then_loads_namespace(
    test_case: ScenarioNamespaceConfigTestCase, tmp_path: Path
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "duckdb"\n[scenario]\nrun_namespace = "{test_case.project}"\n'
    )
    (tmp_path / "sqlbuild_local.toml").write_text(
        f'[scenario]\nrun_namespace = "{test_case.local}"\n'
    )
    inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    assert (
        resolve_effective_scenario_config(
            project_config=inputs.project_config, local_config=inputs.local_config
        ).run_namespace
        == test_case.expected_value
    )


@pytest.mark.parametrize(
    "test_case",
    (
        InvalidScenarioNamespaceConfigTestCase("project empty", "sqlbuild_project.toml", '""'),
        InvalidScenarioNamespaceConfigTestCase(
            "local invalid characters", "sqlbuild_local.toml", '"job/1"'
        ),
        InvalidScenarioNamespaceConfigTestCase("project numeric", "sqlbuild_project.toml", "42"),
        InvalidScenarioNamespaceConfigTestCase("local boolean", "sqlbuild_local.toml", "true"),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_config_namespace_when_discovering_then_schema_validation_rejects(
    test_case: InvalidScenarioNamespaceConfigTestCase, tmp_path: Path
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    with (tmp_path / test_case.filename).open("a") as config:
        config.write(f"\n[scenario]\nrun_namespace = {test_case.value_toml}\n")
    with pytest.raises(ProjectConfigError, match=test_case.expected_error):
        discover_project_inputs(project_dir=tmp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
