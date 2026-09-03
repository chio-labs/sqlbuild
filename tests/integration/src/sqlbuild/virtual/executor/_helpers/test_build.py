from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

import sqlbuild.virtual.executor._helpers.build as virtual_build_module
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.executor.build.models import BuildExecutionResult, BuildRuntimeParams
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.microbatches.models import MicrobatchScope
from sqlbuild.microbatches.types import MicrobatchEventStore
from sqlbuild.virtual.executor.classes.microbatch_lease_manager import (
    VirtualMicrobatchLeaseManager,
)
from sqlbuild.virtual.executor.models import (
    VirtualBuildHooks,
    VirtualBuildOptions,
    VirtualBuildPipelineResult,
    VirtualEnvironmentNames,
)
from sqlbuild.virtual.state.classes.duckdb import DuckDbStateBackend
from sqlbuild.virtual.state.classes.microbatch_store import VirtualMicrobatchEventStore
from sqlbuild.virtual.state.models import StateBackendConfig, StateLockRecord
from sqlbuild.virtual.state.types import StateBackendName
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
    VirtualMicrobatchResolverTestCase,
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


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualMicrobatchResolverTestCase(
            description="downstream-only producer uses target virtual state realm",
            expected_environment_name="feature_env",
            expected_scope_kind="virtual_physical",
            expected_selected_model_names=("daily_events",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_downstream_only_virtual_build_when_resolving_producer_then_state_stays_in_target_environment(
    test_case: VirtualMicrobatchResolverTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    warehouse_config: dict[str, object] = {"database": str(tmp_path / "warehouse.duckdb")}
    connection: Any = adapter.connect(warehouse_config)
    connection.execute("CREATE SCHEMA physical")
    connection.execute("CREATE TABLE physical.upstream_events (event_time TIMESTAMP)")
    connection.execute("CREATE TABLE physical.daily_events (event_time TIMESTAMP)")
    consumer: ModelPlanEntry = ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="daily_events"),
        name="daily_events",
        relative_path=Path("models/daily_events.sql"),
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction.INCREMENTAL_DELETE_INSERT,
        reason=PlanReason.NORMAL_INCREMENTAL,
        destination=CompiledRelationLocation(
            None, "physical", "daily_events", "physical.daily_events"
        ),
        fingerprint_query_sql="SELECT event_time FROM physical.upstream_events",
        fingerprint_version_hash="consumer-v1",
        resolved_sql="SELECT event_time FROM physical.upstream_events",
        logical_ddl="",
    )
    producer_location: CompiledRelationLocation = CompiledRelationLocation(
        None, "physical", "upstream_events", "physical.upstream_events"
    )
    captured_scopes: list[MicrobatchScope] = []

    def capture_pipeline(
        *, plan: PlanOutput, runtime: BuildRuntimeParams, **_kwargs: object
    ) -> BuildExecutionResult:
        state_resolver: (
            Callable[[ModelPlanEntry, object], tuple[MicrobatchEventStore, MicrobatchScope]] | None
        ) = runtime.microbatch_state_resolver
        location_resolver: (
            Callable[
                [str, CompiledRelationLocation, str | None, object],
                tuple[MicrobatchEventStore, MicrobatchScope],
            ]
            | None
        ) = runtime.microbatch_location_state_resolver
        assert state_resolver is not None
        assert location_resolver is not None
        selected_store, selected_scope = state_resolver(consumer, connection)
        producer_store, producer_scope = location_resolver(
            "upstream_events", producer_location, "producer-v1", connection
        )
        assert isinstance(selected_store, VirtualMicrobatchEventStore)
        assert isinstance(producer_store, VirtualMicrobatchEventStore)
        assert tuple(entry.name for entry in plan.model_entries) == (
            test_case.expected_selected_model_names
        )
        captured_scopes.extend((selected_scope, producer_scope))
        return BuildExecutionResult(status=BuildStatus.SUCCESS)

    monkeypatch.setattr(virtual_build_module, "load_custom_materializations", Mock(return_value={}))
    monkeypatch.setattr(
        virtual_build_module, "load_custom_prepare_version_functions", Mock(return_value={})
    )
    monkeypatch.setattr(virtual_build_module, "run_build_pipeline", capture_pipeline)
    state_config: StateBackendConfig = StateBackendConfig(
        backend=StateBackendName.DUCKDB,
        schema="state_schema",
        connection={"database": str(tmp_path / "state.duckdb")},
    )
    runtime: Any = virtual_build_module._VirtualBuildRuntime(
        project_dir=tmp_path,
        discovered_inputs=Mock(loader_functions=()),
        adapter=adapter,
        connection_config=warehouse_config,
        options=VirtualBuildOptions(),
        hooks=VirtualBuildHooks(),
        backend=DuckDbStateBackend(),
        config=state_config,
        names=VirtualEnvironmentNames(target_vde_name=test_case.expected_environment_name),
    )
    python_plan: Mock = Mock()
    python_plan.lifecycle_plan.ingress_loader_names = frozenset()
    try:
        downstream_only_plan: PlanOutput = PlanOutput(
            model_entries=(consumer,),
            model_locations={"upstream_events": producer_location},
        )
        virtual_build_module._execute_virtual_build_plan(
            runtime=runtime,
            plan=Mock(executor_plan_output=downstream_only_plan),
            project=CompiledProject(
                run_id="virtual-run",
                effective_target_name="test",
                effective_connection=warehouse_config,
                effective_vars={},
            ),
            python_plan=python_plan,
            reads=Mock(
                semantics=Mock(expected_version_hashes={"daily_events": "consumer-v1"}),
                available_seed_physical_relations={},
            ),
            exec_hooks=Mock(
                on_node_start=None,
                on_node_complete=None,
                on_sub_progress=None,
                on_scheduler_state=None,
                on_statement_complete=None,
            ),
            ingress_load_results=(),
            microbatch_lease_check=Mock(),
        )
    finally:
        adapter.close(connection)

    selected_scope, producer_scope = captured_scopes
    assert selected_scope.scope_kind == test_case.expected_scope_kind
    assert producer_scope.scope_kind == test_case.expected_scope_kind
    assert selected_scope.virtual_environment_name == test_case.expected_environment_name
    assert producer_scope.virtual_environment_name == test_case.expected_environment_name
    assert selected_scope.scope_key.split(":", 3)[:3] == producer_scope.scope_key.split(":", 3)[:3]
