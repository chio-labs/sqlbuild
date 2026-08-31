from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import sqlbuild.virtual.executor._helpers.build as virtual_build_module
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult, BuildRuntimeParams
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.virtual.executor.classes.microbatch_lease_manager import (
    VirtualMicrobatchLeaseManager,
)
from sqlbuild.virtual.executor.models import (
    VirtualBuildHooks,
    VirtualBuildOptions,
    VirtualBuildPipelineResult,
)
from sqlbuild.virtual.state.classes.duckdb import DuckDbStateBackend
from sqlbuild.virtual.state.models import StateLockRecord
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    build_virtual_wide_dag_repo_files,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)
from tests.integration.src.sqlbuild.virtual.executor._helpers._test_types import (
    VirtualBuildPipelineTestCase,
    VirtualLeaseAcquireBoundaryTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildPipelineTestCase(
            description="physical destinations and runtime are scoped before pipeline starts",
            expected_schema="dev__sqb_physical",
            expected_model_names=("model_01", "model_02", "model_03", "model_04"),
            expected_target="dev",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_build_when_pipeline_starts_then_schema_and_runtime_are_project_scoped(
    test_case: VirtualBuildPipelineTestCase,
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

    def fake_run_build_pipeline(
        *, plan: PlanOutput, runtime: BuildRuntimeParams, **kwargs: Any
    ) -> BuildExecutionResult:
        assert runtime.runtime_dir == project_dir / "target"
        assert runtime.target == test_case.expected_target
        assert all(
            entry.destination.schema == test_case.expected_schema for entry in plan.model_entries
        )
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
        options=VirtualBuildOptions(concurrency=8),
        hooks=VirtualBuildHooks(),
    )

    assert result.execution_result.status == BuildStatus.SUCCESS
    assert tuple(sorted(observed_model_names)) == test_case.expected_model_names


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualLeaseAcquireBoundaryTestCase(
            description="interrupt after acquire still releases model version lease",
            expected_error_type=KeyboardInterrupt,
            expected_active_lock_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupt_after_lease_acquire_when_virtual_build_unwinds_then_lease_is_released(
    test_case: VirtualLeaseAcquireBoundaryTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_acquire_boundary",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "models/orders.sql": (
                "MODEL (materialized incremental, incremental_strategy merge, "
                "unique_key [id], full_refresh true);\n\nSELECT 1 AS id\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr
    original_acquire: Callable[..., None] = VirtualMicrobatchLeaseManager.acquire

    def _acquire_then_interrupt(
        self: VirtualMicrobatchLeaseManager,
        **kwargs: Any,
    ) -> None:
        original_acquire(self, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(VirtualMicrobatchLeaseManager, "acquire", _acquire_then_interrupt)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    with pytest.raises(test_case.expected_error_type):
        virtual_build_module.run_virtual_build(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            adapter=DuckDbAdapter(),
            connection_config={"database": str(project_dir / "warehouse.duckdb")},
            options=VirtualBuildOptions(),
            hooks=VirtualBuildHooks(),
        )
    backend: DuckDbStateBackend = DuckDbStateBackend()
    connection: Any = backend.connect({"database": str(project_dir / "state.duckdb")})
    try:
        active_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection=connection,
            schema="sqlbuild_state",
        )
    finally:
        backend.close(connection)
    assert len(active_locks) == test_case.expected_active_lock_count
