from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from sqlbuild.cli.commands._helpers.scenario_execution import runner
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlScenario,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile


class ScenarioProgressStream(StringIO):
    def __init__(self, *, tty: bool) -> None:
        super().__init__()
        self._tty: bool = tty

    def isatty(self) -> bool:
        return self._tty


def configure_scenario_runner(
    *,
    monkeypatch: pytest.MonkeyPatch,
    stream: ScenarioProgressStream,
    compile_project: Any,
) -> None:
    discovered_inputs: Mock = Mock()
    discovered_inputs.project_config.name = "project"
    monkeypatch.setattr(runner.sys, "stdout", stream)
    monkeypatch.setattr(runner, "supports_color", lambda: False)
    monkeypatch.setattr(runner, "discover_project_inputs", lambda **_: discovered_inputs)
    monkeypatch.setattr(runner, "resolve_effective_adapter_name", lambda **_: "duckdb")
    monkeypatch.setattr(runner, "resolve_adapter", lambda **_: Mock())
    monkeypatch.setattr(runner, "resolve_project_connection_config", lambda **_: {})
    monkeypatch.setattr(runner, "resolve_external_sql_reference_resolver", lambda **_: None)
    monkeypatch.setattr(runner, "run_compile_only_pipeline", compile_project)
    monkeypatch.setattr(runner, "select_scenarios", lambda **_: ())
    monkeypatch.setattr(runner, "run_warehouse_scenarios", lambda **_: 0)


def build_project_with_scenarios(project_dir: Path) -> CompiledProject:
    scenarios: tuple[CompiledSqlScenario, ...] = tuple(
        CompiledSqlScenario(
            key=CompiledObjectKey(CompiledResourceType.SQL_SCENARIO, scenario_name),
            name=scenario_name,
            scenario_file=DiscoveredSqlScenarioFile(
                file_path=project_dir / relative_path,
                relative_path=Path(relative_path),
                contents="SCENARIO();\n\nSELECT 1\n",
                header_values={},
                sql_body="SELECT 1",
                name=scenario_name,
            ),
            sql_body="SELECT 1",
        )
        for scenario_name, relative_path in (
            ("orders_paid", "tests/scenarios/orders/paid.sql"),
            ("orders_refund", "tests/scenarios/orders/refund.sql"),
        )
    )
    return CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        sql_scenarios=scenarios,
    )
