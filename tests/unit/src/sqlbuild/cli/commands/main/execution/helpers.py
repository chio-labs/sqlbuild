"""Test helpers for build execution command boundaries."""

import sys
from contextlib import nullcontext
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from sqlbuild import _native as native
from sqlbuild._native import (
    CompiledObjectKey,
    CompiledSqlScenario,
    DiscoveredProjectInputs,
    DiscoveredSqlScenarioFile,
    LocalConfig,
    ProjectConfig,
)
from sqlbuild.adapter.discovery.main import resolve_adapter as adapters_module
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.diagnostics.main import process_resource_reporting as resource_reporting_module
from sqlbuild.executor.pipeline.main import run as executor_run_module
from tests.unit.src.sqlbuild.presentation.helpers import use_plain_terminal


def fail_build_discovery(*, monkeypatch: pytest.MonkeyPatch, error: BaseException) -> Mock:
    """Make project discovery raise and record the debug resource reporter calls."""

    def discover(**_kwargs: object) -> DiscoveredProjectInputs:
        raise error

    reporter: Mock = Mock(return_value=nullcontext())
    monkeypatch.setattr(native, "discover_project_inputs", discover)
    monkeypatch.setattr(resource_reporting_module, "process_resource_reporting", reporter)
    return reporter


class ScenarioProgressStream(StringIO):
    """A progress stream that reports whether it is a terminal."""

    def __init__(self, *, tty: bool) -> None:
        super().__init__()
        self._tty: bool = tty

    def isatty(self) -> bool:
        return self._tty


def configure_native_scenario_command(
    *,
    monkeypatch: pytest.MonkeyPatch,
    stream: ScenarioProgressStream,
    compile_project: Any,
) -> None:
    """Isolate the native scenario command from discovery, adapters and the warehouse."""

    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(name="project", adapter="duckdb"),
        local_config=LocalConfig(),
    )
    monkeypatch.setattr(sys, "stdout", stream)
    use_plain_terminal(monkeypatch)
    monkeypatch.setattr(native, "discover_project_inputs", lambda **_: discovered_inputs)
    monkeypatch.setattr(native, "resolve_project_connection_config", lambda **_: {})
    monkeypatch.setattr(native, "run_compile_only_pipeline", compile_project)
    monkeypatch.setattr(adapters_module, "resolve_adapter", lambda **_: Mock())
    monkeypatch.setattr(native, "resolve_external_sql_reference_resolver", lambda **_: None)
    monkeypatch.setattr(executor_run_module, "run_scenario_test_pipeline", lambda **_: ())


def build_compiled_scenario_project(project_dir: Path) -> Mock:
    """A compile result with one scenario under tests/scenarios."""

    scenario_file: DiscoveredSqlScenarioFile = DiscoveredSqlScenarioFile(
        file_path=project_dir / "tests/scenarios/orders_paid.sql",
        relative_path=Path("tests/scenarios/orders_paid.sql"),
        contents="SCENARIO(description 'Test scenario.');\n\nSELECT 1\n",
        header_values={},
        sql_body="SELECT 1",
        name="orders_paid",
    )
    pipeline_result: Mock = Mock()
    pipeline_result.project.sql_scenarios = (
        CompiledSqlScenario(
            key=CompiledObjectKey(CompiledResourceType.SQL_SCENARIO, "orders_paid"),
            name="orders_paid",
            scenario_file=scenario_file,
            sql_body="SELECT 1",
        ),
    )
    return pipeline_result
