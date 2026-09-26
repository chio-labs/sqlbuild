"""Resolve scenario namespace overrides before planning or warehouse work."""

from __future__ import annotations

import os
from dataclasses import replace

from sqlbuild.cli.commands.constants import SCENARIO_CLI_INVALID_NAMESPACE
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import ScenarioRunNamespace
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.main.parse_scenario_run_namespace import (
    parse_scenario_run_namespace,
)


def resolve_scenario_namespace(
    *, inputs: DiscoveredProjectInputs, cli_value: str | None
) -> tuple[DiscoveredProjectInputs, ScenarioRunNamespace]:
    """Apply CLI > environment > local config > project config precedence."""

    candidates: tuple[tuple[str | None, str], ...] = (
        (cli_value, "cli"),
        (os.environ.get("SQLBUILD_SCENARIO_NAMESPACE"), "env"),
        (inputs.local_config.scenario.run_namespace, "local config"),
        (inputs.project_config.scenario.run_namespace, "project config"),
    )
    value: str | None
    source: str
    for value, source in candidates:
        if value is None:
            continue
        try:
            value = parse_scenario_run_namespace(value)
        except SpecConfigError as exc:
            raise CliUserError(str(exc), code=SCENARIO_CLI_INVALID_NAMESPACE) from exc
        return replace(
            inputs,
            local_config=replace(
                inputs.local_config,
                scenario=replace(inputs.local_config.scenario, run_namespace=value),
            ),
        ), ScenarioRunNamespace(value=value, source=source)
    return inputs, ScenarioRunNamespace()
