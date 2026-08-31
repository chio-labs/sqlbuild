"""Virtual statement diagnostic callback scope tests."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.models import CostResourceContext
from sqlbuild.executor.build.models import BuildCallbacks, BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.virtual.executor._helpers import build as virtual_build_module
from sqlbuild.virtual.executor.models import VirtualBuildExecutionHooks
from tests.unit.src.sqlbuild.virtual.executor._helpers._test_types import (
    VirtualStatementScopeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualStatementScopeTestCase(
            description="ingress and finalization inherit callback and reset after each scope",
            expected_phases=("virtual_ingress", "virtual_finalize"),
            expected_callback_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_statement_callback_when_executing_then_all_outer_scopes_propagate_and_reset(
    test_case: VirtualStatementScopeTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback: Mock = Mock()
    observed_phases: list[str] = []
    observed_callbacks: list[object] = []
    reset_contexts: list[CostResourceContext | None] = []

    def capture_ingress(**_kwargs: object) -> None:
        context: CostResourceContext | None = CostContext.current()
        assert context is not None
        observed_phases.append(context.phase)
        observed_callbacks.append(context.on_statement_complete)

    def capture_finalize(**_kwargs: object) -> tuple[object, ...]:
        context: CostResourceContext | None = CostContext.current()
        assert context is not None
        observed_phases.append(context.phase)
        observed_callbacks.append(context.on_statement_complete)
        return ()

    def capture_execution(**_kwargs: object) -> BuildExecutionResult:
        reset_contexts.append(CostContext.current())
        return BuildExecutionResult(status=BuildStatus.SUCCESS)

    monkeypatch.setattr(virtual_build_module, "_run_ingress_python_nodes", capture_ingress)
    monkeypatch.setattr(
        virtual_build_module,
        "_execute_virtual_build_plan",
        capture_execution,
    )
    monkeypatch.setattr(virtual_build_module, "_persist_successful_virtual_build", Mock())
    monkeypatch.setattr(virtual_build_module, "_run_read_side_python_nodes", capture_finalize)
    project: CompiledProject = CompiledProject(
        run_id="scope-run",
        effective_target_name="test",
        effective_connection={},
        effective_vars={},
    )
    runtime: Mock = Mock(project_dir=Path("."))
    rewritten: Mock = Mock(project=project)
    graph: Mock = Mock(project=project)

    virtual_build_module._execute_leased_virtual_build(
        runtime=runtime,
        graph=graph,
        reads=Mock(),
        rewritten=rewritten,
        plan=Mock(),
        python_plan=Mock(),
        exec_hooks=VirtualBuildExecutionHooks(on_statement_complete=callback),
        microbatch_lease_check=Mock(),
        model_version_leases=(),
    )

    assert tuple(observed_phases) == test_case.expected_phases
    assert observed_callbacks == [callback] * test_case.expected_callback_count
    assert reset_contexts == [None]
    assert CostContext.current() is None


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualStatementScopeTestCase(
            description="build pipeline receives statement diagnostics",
            expected_phases=("build",),
            expected_callback_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_execution_callback_when_building_then_pipeline_receives_it(
    test_case: VirtualStatementScopeTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback: Mock = Mock()
    observed_phases: list[str] = []
    observed_callbacks: list[object] = []

    def capture_build(**kwargs: object) -> BuildExecutionResult:
        callbacks: BuildCallbacks = cast(BuildCallbacks, kwargs["callbacks"])
        observed_phases.append("build")
        observed_callbacks.append(callbacks.on_statement_complete)
        return BuildExecutionResult(status=BuildStatus.SUCCESS)

    monkeypatch.setattr(virtual_build_module, "load_custom_materializations", Mock(return_value={}))
    monkeypatch.setattr(
        virtual_build_module, "load_custom_prepare_version_functions", Mock(return_value={})
    )
    monkeypatch.setattr(virtual_build_module, "run_build_pipeline", capture_build)
    project: CompiledProject = CompiledProject(
        run_id="execution-scope-run",
        effective_target_name="test",
        effective_connection={},
        effective_vars={},
    )
    runtime: Mock = Mock(project_dir=Path("."), connection_config={}, adapter=Mock())
    runtime.options.concurrency = 1
    runtime.discovered_inputs.loader_functions = ()
    python_plan: Mock = Mock()
    python_plan.lifecycle_plan.ingress_loader_names = frozenset()

    virtual_build_module._execute_virtual_build_plan(
        runtime=runtime,
        plan=Mock(),
        project=project,
        python_plan=python_plan,
        reads=Mock(available_seed_physical_relations={}),
        exec_hooks=VirtualBuildExecutionHooks(on_statement_complete=callback),
        ingress_load_results=(),
        microbatch_lease_check=Mock(),
    )

    assert tuple(observed_phases) == test_case.expected_phases
    assert observed_callbacks == [callback] * test_case.expected_callback_count
    assert CostContext.current() is None
