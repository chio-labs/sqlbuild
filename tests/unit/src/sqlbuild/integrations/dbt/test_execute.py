from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from sqlbuild import _native as execute_module
from sqlbuild import _native as phases_module
from sqlbuild import _native as plan_module
from sqlbuild._native import (
    DbtCombinedGraph,
    build_dbt_interop_plan,
    build_failed_sqlbuild_model_names,
    build_merged_dbt_execution_argv,
    execute_dbt_commands,
)
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.main.runtime import _execute_json_event_stream as event_module
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandExecutionResult,
    DbtInteropCompiledProject,
    DbtInteropExecutionRequest,
    DbtInteropInvocation,
    DbtInteropPlan,
    DbtInteropPlanResolution,
    DbtInteropRoutedArgs,
    DbtInteropSelectionResult,
    DbtLsNode,
    DbtManifestIndex,
    DbtNodeExecutionResult,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtCompileFullRefreshPipelineTestCase,
    DbtExecutionSelectionStatusTestCase,
    DbtExecutionSummaryFooterTestCase,
    DbtResultBackfillTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    CompileOnlyDbtRunner,
    build_orders_dbt_graph,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCompileFullRefreshPipelineTestCase(
            description="plan uses ordinary current dbt compile",
            command="plan",
            expected_full_refresh_values=(False,),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ordinary_plan_when_compiling_then_uses_single_current_compile(
    test_case: DbtCompileFullRefreshPipelineTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner: CompileOnlyDbtRunner = CompileOnlyDbtRunner()
    manifest: DbtManifestIndex = DbtManifestIndex(
        models_by_unique_id={},
        models_by_name={},
        models_by_package_and_name={},
    )
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=DbtInteropCommand.PLAN,
        dbt_command_argv=("dbt", "ls"),
        dbt_ls_nodes=(),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
    )
    invocation: SimpleNamespace = SimpleNamespace(
        runner=runner,
        dbt_options=DbtCliOptions(project_dir=Path("/dbt")),
        discovered_inputs=SimpleNamespace(),
        dbt_vars={},
        effective_sqlbuild_args=(),
    )
    compiled: SimpleNamespace = SimpleNamespace(
        adapter_name="duckdb", adapter=object(), project=object()
    )
    monkeypatch.setattr(plan_module, "resolve_dbt_execution_invocation", lambda request: invocation)
    monkeypatch.setattr(
        plan_module,
        "load_compiled_dbt_manifest",
        lambda **kwargs: (
            runner.compile(
                options=invocation.dbt_options,
                full_refresh=cast(bool, kwargs["full_refresh"]),
            ),
            manifest,
        )[1],
    )
    monkeypatch.setattr(plan_module, "compile_dbt_interop_project", lambda **kwargs: compiled)
    monkeypatch.setattr(
        plan_module,
        "resolve_dbt_interop_plan",
        lambda **kwargs: DbtInteropPlanResolution(
            graph=cast(DbtCombinedGraph, object()), plan=plan
        ),
    )
    monkeypatch.setattr(plan_module, "attach_sqlbuild_plan_output", lambda **kwargs: plan)

    result: DbtInteropPlan = plan_module.plan_dbt_interop_from_project(
        project_dir=Path("/project"),
        args=(),
        dbt_runner=runner,
    )

    assert result is plan
    assert tuple(runner.compile_full_refresh_values) == test_case.expected_full_refresh_values


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCompileFullRefreshPipelineTestCase(
            description="run uses current compile only",
            command="run",
            expected_full_refresh_values=(False,),
        ),
        DbtCompileFullRefreshPipelineTestCase(
            description="build uses current compile only",
            command="build",
            expected_full_refresh_values=(False,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ordinary_execution_when_compiling_then_never_uses_dbt_state(
    test_case: DbtCompileFullRefreshPipelineTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command: DbtInteropCommand = DbtInteropCommand(test_case.command)
    runner: CompileOnlyDbtRunner = CompileOnlyDbtRunner()
    manifest: DbtManifestIndex = DbtManifestIndex(
        models_by_unique_id={},
        models_by_name={},
        models_by_package_and_name={},
    )
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=command,
        dbt_command_argv=("dbt", command.value),
        dbt_ls_nodes=(),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
    )
    invocation: DbtInteropInvocation = DbtInteropInvocation(
        dbt_executable="dbt",
        output_stream=StringIO(),
        dbt_output_stream=StringIO(),
        routed=DbtInteropRoutedArgs(command=command),
        discovered_inputs=cast(DiscoveredProjectInputs, SimpleNamespace()),
        effective_sqlbuild_args=(),
        dbt_options=DbtCliOptions(project_dir=Path("/dbt")),
        dbt_vars={},
        runner=runner,
    )
    compiled: DbtInteropCompiledProject = DbtInteropCompiledProject(
        adapter_name="duckdb",
        adapter=cast(BaseAdapter, SimpleNamespace()),
        project=cast(CompiledProject, SimpleNamespace()),
    )
    monkeypatch.setattr(
        execute_module, "resolve_dbt_execution_invocation", lambda request: invocation
    )
    monkeypatch.setattr(
        execute_module,
        "load_compiled_dbt_manifest",
        lambda **kwargs: (
            runner.compile(
                options=invocation.dbt_options,
                full_refresh=cast(bool, kwargs["full_refresh"]),
            ),
            manifest,
        )[1],
    )
    monkeypatch.setattr(execute_module, "compile_dbt_interop_project", lambda **kwargs: compiled)
    monkeypatch.setattr(
        execute_module,
        "resolve_dbt_interop_plan",
        lambda **kwargs: DbtInteropPlanResolution(
            graph=build_orders_dbt_graph(),
            plan=plan,
        ),
    )
    monkeypatch.setattr(execute_module, "write_dbt_execution_plan_text", lambda **kwargs: None)
    monkeypatch.setattr(
        execute_module,
        "execute_dbt_without_state_tracking",
        lambda **kwargs: DbtCommandExecutionResult(returncode=0),
    )
    monkeypatch.setattr(execute_module, "write_dbt_execution_summary", lambda **kwargs: None)
    monkeypatch.setattr(
        execute_module,
        "resolve_sqlbuild_execution_plan_output",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(execute_module, "write_sqlbuild_skip_notice", lambda **kwargs: None)

    result: int = execute_module.execute_dbt_interop_from_project(
        DbtInteropExecutionRequest(command=command, project_dir=Path("/project"), args=())
    )

    assert result == 0
    assert tuple(runner.compile_full_refresh_values) == test_case.expected_full_refresh_values


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionSummaryFooterTestCase(
            description="ordinary dbt execution does not install a state write callback",
            node_statuses=("success",),
            expected_footer="no-state-callback",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ordinary_dbt_events_when_executing_then_no_fingerprint_or_watermark_callback_is_used(
    test_case: DbtExecutionSummaryFooterTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def execute_commands(**kwargs: object) -> DbtCommandExecutionResult:
        observed.update(kwargs)
        return DbtCommandExecutionResult(returncode=0)

    monkeypatch.setattr(phases_module, "execute_dbt_commands", execute_commands)
    command: DbtInteropCommand = DbtInteropCommand.RUN
    invocation: DbtInteropInvocation = DbtInteropInvocation(
        dbt_executable="dbt",
        output_stream=StringIO(),
        dbt_output_stream=StringIO(),
        routed=DbtInteropRoutedArgs(command=command),
        discovered_inputs=cast(DiscoveredProjectInputs, SimpleNamespace()),
        effective_sqlbuild_args=(),
        dbt_options=DbtCliOptions(project_dir=Path("/dbt")),
        dbt_vars={},
        runner=cast(object, SimpleNamespace()),
    )

    result: DbtCommandExecutionResult = phases_module.execute_dbt_without_state_tracking(
        request=DbtInteropExecutionRequest(command=command, project_dir=Path("/project"), args=()),
        invocation=invocation,
        merged_dbt_argv=("dbt", "run"),
    )

    assert result.returncode == 0
    assert "on_node_result" not in observed
    assert test_case.expected_footer == "no-state-callback"


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionSummaryFooterTestCase(
            description="actual dbt failure blocks only downstream SQLBuild models",
            node_statuses=("error",),
            expected_footer="local_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_actual_dbt_failure_when_resolving_blockers_then_blocks_downstream_sqlbuild_work(
    test_case: DbtExecutionSummaryFooterTestCase,
) -> None:
    graph: DbtCombinedGraph = build_orders_dbt_graph()
    dbt_unique_id: str = "model.analytics.orders"

    result: tuple[str, ...] = build_failed_sqlbuild_model_names(
        graph=graph,
        manifest=DbtManifestIndex(
            models_by_unique_id={},
            models_by_name={},
            models_by_package_and_name={},
        ),
        node_results=(
            DbtNodeExecutionResult(
                unique_id=dbt_unique_id,
                resource_type="model",
                node_name="orders",
                status=test_case.node_statuses[0],
                index=1,
                total=1,
                execution_time=0.1,
            ),
        ),
    )

    assert result == (test_case.expected_footer,)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionSummaryFooterTestCase(
            description="failed dbt test blocks SQLBuild models downstream of its tested model",
            node_statuses=("fail",),
            expected_footer="local_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failed_dbt_test_when_resolving_blockers_then_blocks_tested_model_downstream(
    test_case: DbtExecutionSummaryFooterTestCase,
) -> None:
    graph: DbtCombinedGraph = build_orders_dbt_graph()
    dbt_unique_id: str = "model.analytics.orders"
    test_unique_id: str = "test.analytics.unique_orders.0123456789"
    manifest: DbtManifestIndex = DbtManifestIndex(
        models_by_unique_id={},
        models_by_name={},
        models_by_package_and_name={},
        validation_depends_on_nodes_by_unique_id={test_unique_id: (dbt_unique_id,)},
    )

    result: tuple[str, ...] = build_failed_sqlbuild_model_names(
        graph=graph,
        manifest=manifest,
        node_results=(
            DbtNodeExecutionResult(
                unique_id=test_unique_id,
                resource_type="test",
                node_name="unique_orders",
                status=test_case.node_statuses[0],
                index=1,
                total=1,
                execution_time=0.1,
            ),
        ),
    )

    assert result == (test_case.expected_footer,)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionSummaryFooterTestCase(
            description="dbt native state and defer survive selector merging",
            node_statuses=(),
            expected_footer="state:modified",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_native_state_when_building_execution_argv_then_preserves_native_options(
    test_case: DbtExecutionSummaryFooterTestCase,
) -> None:
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_ls_nodes=(DbtLsNode(unique_id="model.analytics.orders"),),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
        dbt_required_selector_terms=("fqn:analytics.required",),
    )
    options: DbtCliOptions = DbtCliOptions(
        project_dir=Path("/dbt"),
        state=Path("/state"),
        defer=True,
    )

    selector: str = cast(str, test_case.expected_footer)
    result: tuple[str, ...] | None = build_merged_dbt_execution_argv(
        command=DbtInteropCommand.BUILD,
        options=options,
        routed_args=("--select", selector),
        plan=plan,
    )

    assert result == (
        "dbt",
        "build",
        "--project-dir",
        "/dbt",
        "--state",
        "/state",
        "--defer",
        "--select",
        selector,
        "fqn:analytics.required",
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionSelectionStatusTestCase(
            description="planned dbt tests bypass execution-time selection",
            expected_total=1,
            expected_output_fragment="dbt execution",
            expected_completion_fragment="Resolving dbt execution selection",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_planned_dbt_tests_when_executing_then_does_not_resolve_selection_again(
    test_case: DbtExecutionSelectionStatusTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoSelectionRunner:
        def invoke(self, **kwargs: object) -> object:
            pytest.fail(f"unexpected execution-time dbt selection: {kwargs}")

    planned_node: DbtLsNode = DbtLsNode(
        unique_id="test.analytics.not_null_fact_orders_order_id",
        resource_type="test",
        name="not_null_fact_orders_order_id",
    )
    streamed_results: tuple[DbtNodeExecutionResult, ...] = (
        DbtNodeExecutionResult(
            unique_id=planned_node.unique_id,
            resource_type="test",
            node_name="not_null_fact_orders_order_id",
            status="pass",
            index=1,
            total=1,
            execution_time=0.1,
        ),
        DbtNodeExecutionResult(
            unique_id="model.analytics.fact_orders",
            resource_type="model",
            node_name="fact_orders",
            status="success",
            index=2,
            total=2,
            execution_time=0.1,
        ),
    )
    monkeypatch.setattr(
        event_module,
        "execute_dbt_json_event_stream",
        lambda **kwargs: (0, streamed_results),
    )
    progress_stream: StringIO = StringIO()

    result: DbtCommandExecutionResult = execute_dbt_commands(
        runner=cast(DbtRunner, NoSelectionRunner()),
        options=DbtCliOptions(project_dir=Path("/dbt")),
        merged_argv=("dbt", "test", "--select", planned_node.unique_id),
        progress_stream=progress_stream,
        stdout_stream=StringIO(),
        use_color=False,
        expected_nodes=(planned_node,),
    )

    assert len(result.node_results) == test_case.expected_total
    assert result.node_results[0].unique_id == planned_node.unique_id
    assert test_case.expected_output_fragment in progress_stream.getvalue()
    assert test_case.expected_completion_fragment not in progress_stream.getvalue()


@pytest.mark.parametrize(
    "test_case",
    [
        DbtResultBackfillTestCase(
            description="unicode message takes precedence over failures",
            message="  café\u2003",
            failures=3,
            expected_message="café",
        ),
        DbtResultBackfillTestCase(
            description="blank message falls back to failure count",
            message="\u2003",
            failures=3,
            expected_message="3 failure(s)",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_streamed_nodes_when_finalizing_then_backfills_selected_artifact_results(
    test_case: DbtResultBackfillTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    streamed: DbtNodeExecutionResult = DbtNodeExecutionResult(
        unique_id="model.analytics.orders",
        resource_type="model",
        node_name="orders",
        status="error",
        index=1,
        total=2,
        execution_time=0.25,
    )
    (tmp_path / "run_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {"unique_id": streamed.unique_id, "status": "error"},
                    {
                        "unique_id": "model.analytics.customers",
                        "status": "skipped",
                        "message": test_case.message,
                        "failures": test_case.failures,
                    },
                    {"unique_id": "model.analytics.inventory", "status": "success"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        event_module, "execute_dbt_json_event_stream", lambda **kwargs: (1, (streamed,))
    )
    output: StringIO = StringIO()
    callbacks: list[DbtNodeExecutionResult] = []
    progress: list[str] = []

    result: DbtCommandExecutionResult = execute_dbt_commands(
        runner=DbtRunner(),
        options=DbtCliOptions(target_path=tmp_path),
        merged_argv=("dbt", "build"),
        progress_stream=StringIO(),
        stdout_stream=output,
        use_color=False,
        expected_nodes=(
            DbtLsNode(unique_id=streamed.unique_id),
            DbtLsNode(unique_id="model.analytics.customers"),
        ),
        on_node_result=callbacks.append,
        on_progress=progress.append,
    )

    assert result.returncode == 1
    assert result.node_results[0] == streamed
    assert len(result.node_results) == 2
    appended: DbtNodeExecutionResult = result.node_results[1]
    assert appended.unique_id == "model.analytics.customers"
    assert appended.status == "skipped"
    assert (appended.index, appended.total) == (2, 3)
    assert appended.messages[0].message == test_case.expected_message
    assert callbacks == [appended]
    assert progress == ["Finalizing dbt run...", "Finalized dbt run."]
    assert "customers" in output.getvalue()
    assert "inventory" not in output.getvalue()
