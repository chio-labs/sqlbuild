from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import sqlbuild.virtual.executor.helpers.build as virtual_build_module
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.virtual.executor.models import VirtualBuildPipelineResult
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    build_virtual_wide_dag_repo_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)
from tests.integration.src.sqlbuild.virtual.executor.helpers._test_types import (
    VirtualPhysicalSchemaPreflightTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPhysicalSchemaPreflightTestCase(
            description="physical schema exists before concurrent build pipeline starts",
            expected_schema="dev__sqb_physical",
            expected_model_names=("model_01", "model_02", "model_03", "model_04"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_build_when_pipeline_starts_then_physical_schema_is_prepared(
    test_case: VirtualPhysicalSchemaPreflightTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_schema_preflight",
        repo_files=build_virtual_wide_dag_repo_files(
            model_count=len(test_case.expected_model_names),
        ),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    adapter: DuckDbAdapter = DuckDbAdapter()
    connection_config: dict[str, object] = {
        "database": str(project_dir / "warehouse.duckdb"),
    }
    observed_model_names: list[str] = []

    def fake_run_build_pipeline(*, plan: PlanOutput, **kwargs: Any) -> BuildExecutionResult:
        connection: Any = adapter.connect(connection_config)
        try:
            assert adapter.schema_exists(
                connection,
                database=None,
                schema=test_case.expected_schema,
            )
        finally:
            adapter.close(connection)
        observed_model_names.extend(entry.name for entry in plan.model_entries)
        return BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=tuple(
                ModelExecutionResult(model_name=entry.name, status=ExecutionStatus.SUCCESS)
                for entry in plan.model_entries
            ),
        )

    monkeypatch.setattr(virtual_build_module, "run_build_pipeline", fake_run_build_pipeline)
    monkeypatch.setattr(
        virtual_build_module,
        "_persist_successful_virtual_build",
        lambda **_: None,
    )

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    result: VirtualBuildPipelineResult = virtual_build_module.run_virtual_build(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        concurrency=8,
    )

    assert result.execution_result.status == BuildStatus.SUCCESS
    assert tuple(sorted(observed_model_names)) == test_case.expected_model_names
