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
    CompiledResourceType,
    CompiledSqlScenario,
    DiscoveredSqlScenarioFile,
)
from sqlbuild.adapter.discovery.main import resolve_adapter as adapters_module
from sqlbuild.diagnostics.main import process_resource_reporting as resource_reporting_module
from sqlbuild.executor.pipeline.main import run as executor_run_module
from tests.unit.src.sqlbuild.presentation.helpers import use_plain_terminal


def fail_build_discovery(
    *, monkeypatch: pytest.MonkeyPatch, project_dir: Path, provider_source: str
) -> Mock:
    """Make project discovery fail in a provider module and record debug resource reporting."""

    providers: Path = project_dir / "providers"
    providers.mkdir(parents=True)
    _ = (project_dir / "sqlbuild_project.toml").write_text(
        'name = "shop"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    _ = (providers / "failing.py").write_text(provider_source, encoding="utf-8")
    reporter: Mock = Mock(return_value=nullcontext())
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
    project_dir: Path,
) -> None:
    """Isolate the native scenario command from adapters and the warehouse in an empty project."""

    _ = (project_dir / "sqlbuild_project.toml").write_text(
        'name = "project"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    monkeypatch.setattr(sys, "stdout", stream)
    use_plain_terminal(monkeypatch)
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
