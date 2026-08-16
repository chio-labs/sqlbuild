from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt._helpers.pipeline import execute as dbt_execute_module
from sqlbuild.integrations.dbt._helpers.pipeline import execution_phases as phases_module
from sqlbuild.integrations.dbt._helpers.pipeline.execute import (
    build_failed_sqlbuild_model_names,
    build_merged_dbt_execution_argv,
)
from sqlbuild.integrations.dbt._helpers.planning.plan import build_dbt_interop_plan
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.main.pipeline import execute as execute_module
from sqlbuild.integrations.dbt.main.pipeline import plan as plan_module
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCombinedGraphKey,
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
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtInteropCommand,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtArgvTestCase,
    DbtCompileFullRefreshPipelineTestCase,
    DbtExecutionSelectionStatusTestCase,
    DbtExecutionSummaryFooterTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import CompileOnlyDbtRunner


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
def test_given_ordinary_plan_when_compiling_then_never_compiles_production_ref(
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
        DbtCompileFullRefreshPipelineTestCase(
            description="test keeps intentional full refresh current compile",
            command="test",
            expected_full_refresh_values=(True,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ordinary_execution_when_compiling_then_never_uses_production_ref_or_dbt_state(
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
            graph=DbtCombinedGraph(nodes=frozenset(), upstream_deps={}, downstream_deps={}),
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
        plan=build_dbt_interop_plan(
            command=command,
            dbt_command_argv=("dbt", "run"),
            dbt_ls_nodes=(),
            sqlbuild_command_argvs=(),
            selection=DbtInteropSelectionResult(),
        ),
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
    dbt_key: DbtCombinedGraphKey = DbtCombinedGraphKey(
        owner=DbtCombinedGraphOwner.DBT,
        resource_type=DbtCombinedGraphResourceType.MODEL,
        name="model.analytics.orders",
    )
    sqlbuild_key: DbtCombinedGraphKey = DbtCombinedGraphKey(
        owner=DbtCombinedGraphOwner.SQLBUILD,
        resource_type=DbtCombinedGraphResourceType.MODEL,
        name="local_orders",
    )
    graph: DbtCombinedGraph = DbtCombinedGraph(
        nodes=frozenset((dbt_key, sqlbuild_key)),
        upstream_deps={dbt_key: (), sqlbuild_key: (dbt_key,)},
        downstream_deps={dbt_key: (sqlbuild_key,), sqlbuild_key: ()},
    )

    result: tuple[str, ...] = build_failed_sqlbuild_model_names(
        graph=graph,
        manifest=DbtManifestIndex(
            models_by_unique_id={},
            models_by_name={},
            models_by_package_and_name={},
        ),
        node_results=(
            DbtNodeExecutionResult(
                unique_id=dbt_key.name,
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
    dbt_key: DbtCombinedGraphKey = DbtCombinedGraphKey(
        owner=DbtCombinedGraphOwner.DBT,
        resource_type=DbtCombinedGraphResourceType.MODEL,
        name="model.analytics.orders",
    )
    sqlbuild_key: DbtCombinedGraphKey = DbtCombinedGraphKey(
        owner=DbtCombinedGraphOwner.SQLBUILD,
        resource_type=DbtCombinedGraphResourceType.MODEL,
        name="local_orders",
    )
    graph: DbtCombinedGraph = DbtCombinedGraph(
        nodes=frozenset((dbt_key, sqlbuild_key)),
        upstream_deps={dbt_key: (), sqlbuild_key: (dbt_key,)},
        downstream_deps={dbt_key: (sqlbuild_key,), sqlbuild_key: ()},
    )
    test_unique_id: str = "test.analytics.unique_orders.0123456789"
    manifest: DbtManifestIndex = DbtManifestIndex(
        models_by_unique_id={},
        models_by_name={},
        models_by_package_and_name={},
        validation_depends_on_nodes_by_unique_id={test_unique_id: (dbt_key.name,)},
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
        DbtArgvTestCase(
            description="dbt test executes the exact tests selected during planning",
            select=("fact_orders",),
            exclude=(),
            resource_types=("model", "test", "unit_test"),
            expected_argv=(
                "dbt",
                "test",
                "--project-dir",
                "/dbt",
                "--select",
                "fqn:analytics.not_null_fact_orders_order_id",
                "fqn:analytics.fact_orders_unit",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_planned_dbt_tests_when_building_execution_argv_then_replaces_model_selector(
    test_case: DbtArgvTestCase,
) -> None:
    nodes: tuple[DbtLsNode, ...] = tuple(
        DbtLsNode(
            unique_id=f"{resource_type}.analytics.{name}",
            resource_type=resource_type,
            name=name,
            fqn=("analytics", name),
        )
        for resource_type, name in zip(
            test_case.resource_types,
            ("fact_orders", "not_null_fact_orders_order_id", "fact_orders_unit"),
            strict=True,
        )
    )
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=DbtInteropCommand.TEST,
        dbt_command_argv=("dbt", "ls"),
        dbt_ls_nodes=nodes,
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
    )

    result: tuple[str, ...] | None = build_merged_dbt_execution_argv(
        command=DbtInteropCommand.TEST,
        options=DbtCliOptions(project_dir=Path("/dbt")),
        routed_args=("--select", *test_case.select),
        plan=plan,
    )

    assert result == test_case.expected_argv


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
        dbt_execute_module,
        "execute_dbt_json_event_stream",
        lambda **kwargs: (0, streamed_results),
    )
    progress_stream: StringIO = StringIO()

    result: DbtCommandExecutionResult = dbt_execute_module.execute_dbt_commands(
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
