"""Namespace precedence and rejection before execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.scenario_execution.namespace import resolve_scenario_namespace
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.main.parse_scenario_run_namespace import parse_scenario_run_namespace
from sqlbuild.spec.contracts.main.resolve_effective_scenario_config import (
    resolve_effective_scenario_config,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, ScenarioConfig
from tests.unit.src.sqlbuild.cli.commands._helpers.scenario_execution._test_types import (
    InvalidNamespaceCase,
    InvalidNamespaceConfigCase,
    NamespaceCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        NamespaceCase(
            "CLI wins",
            cli="job-1",
            environment=(("SQLBUILD_SCENARIO_NAMESPACE", "job-2"),),
            local="local",
            project="project",
            expected_value="job-1",
            expected_source="cli",
        ),
        NamespaceCase(
            "environment wins",
            environment=(("SQLBUILD_SCENARIO_NAMESPACE", "job-2"),),
            local="local",
            project="project",
            expected_value="job-2",
            expected_source="env",
        ),
        NamespaceCase(
            "local wins",
            local="local",
            project="project",
            expected_value="local",
            expected_source="local config",
        ),
        NamespaceCase(
            "project fallback",
            project="project",
            expected_value="project",
            expected_source="project config",
        ),
        NamespaceCase("unset preserves default"),
        NamespaceCase(
            "CLI overrides invalid environment",
            cli="job-1",
            environment=(("SQLBUILD_SCENARIO_NAMESPACE", ""),),
            expected_value="job-1",
            expected_source="cli",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_namespace_sources_when_resolving_then_highest_precedence_wins(
    test_case: NamespaceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SQLBUILD_SCENARIO_NAMESPACE", raising=False)
    for key, value in test_case.environment:
        monkeypatch.setenv(key, value)
    inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="orders",
            adapter="duckdb",
            scenario=ScenarioConfig(run_namespace=test_case.project),
        ),
        local_config=LocalConfig(scenario=ScenarioConfig(run_namespace=test_case.local)),
    )
    resolved, namespace = resolve_scenario_namespace(inputs=inputs, cli_value=test_case.cli)
    assert namespace.value == test_case.expected_value
    assert namespace.source == test_case.expected_source
    assert (
        resolve_effective_scenario_config(
            project_config=resolved.project_config, local_config=resolved.local_config
        ).run_namespace
        == test_case.expected_value
    )


@pytest.mark.parametrize(
    "test_case",
    (
        InvalidNamespaceCase("empty", ""),
        InvalidNamespaceCase("whitespace", " "),
        InvalidNamespaceCase("slash", "job/1"),
        InvalidNamespaceCase("colon", "job:1"),
        InvalidNamespaceCase("newline", "job\n"),
        InvalidNamespaceCase("non ASCII", "é"),
        InvalidNamespaceCase("too long", "x" * 129),
        InvalidNamespaceCase("numeric", 42),
        InvalidNamespaceCase("explicit null", None),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_namespace_when_parsing_then_rejects(test_case: InvalidNamespaceCase) -> None:
    with pytest.raises(SpecConfigError, match=test_case.expected_error):
        parse_scenario_run_namespace(test_case.value)


@pytest.mark.parametrize(
    "test_case",
    (
        NamespaceCase("all allowed characters", cli="AZaz09-_.", expected_value="AZaz09-_."),
        NamespaceCase("maximum length", cli="x" * 128, expected_value="x" * 128),
    ),
    ids=lambda case: case.description,
)
def test_given_valid_namespace_when_parsing_then_preserves_value(test_case: NamespaceCase) -> None:
    assert parse_scenario_run_namespace(test_case.cli) == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    (InvalidNamespaceCase("empty environment does not fall back", ""),),
    ids=lambda case: case.description,
)
def test_given_empty_environment_when_resolving_then_does_not_fall_back(
    test_case: InvalidNamespaceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SQLBUILD_SCENARIO_NAMESPACE", str(test_case.value))
    inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="orders", adapter="duckdb", scenario=ScenarioConfig(run_namespace="project")
        ),
        local_config=LocalConfig(),
    )
    with pytest.raises(CliUserError, match=test_case.expected_error):
        resolve_scenario_namespace(inputs=inputs, cli_value=None)


@pytest.mark.parametrize(
    "test_case",
    (NamespaceCase("both config files", project="project", local="local", expected_value="local"),),
    ids=lambda case: case.description,
)
def test_given_project_and_local_config_when_discovering_then_loads_namespace(
    test_case: NamespaceCase, tmp_path: Path
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
        InvalidNamespaceConfigCase("project empty", "sqlbuild_project.toml", '""'),
        InvalidNamespaceConfigCase("local invalid characters", "sqlbuild_local.toml", '"job/1"'),
        InvalidNamespaceConfigCase("project numeric", "sqlbuild_project.toml", "42"),
        InvalidNamespaceConfigCase("local boolean", "sqlbuild_local.toml", "true"),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_config_namespace_when_discovering_then_schema_validation_rejects(
    test_case: InvalidNamespaceConfigCase, tmp_path: Path
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    with (tmp_path / test_case.filename).open("a") as config:
        config.write(f"\n[scenario]\nrun_namespace = {test_case.value_toml}\n")
    with pytest.raises(ProjectConfigError, match=test_case.expected_error):
        discover_project_inputs(project_dir=tmp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
