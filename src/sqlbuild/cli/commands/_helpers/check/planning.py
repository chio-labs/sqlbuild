"""Check command plan compilation phase."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.check.core import (
    check_dependency_closure,
    resolve_selected_check_names,
)
from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.models import CheckCommandRequest, CheckInvocation
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.main.static_command import compile_static_command_context
from sqlbuild.compiler.pipeline.main.static_result import build_static_pipeline_result
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
    StaticCommandContext,
)
from sqlbuild.compiler.planner.main.commands.relation_plan import build_relation_command_plan
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind


def compile_check_plan(
    *, request: CheckCommandRequest, invocation: CheckInvocation
) -> CompilePipelineResult:
    """Compile the project for Python check execution."""

    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=invocation.discovered_inputs
    )
    check_names: frozenset[str] = resolve_selected_check_names(
        graph=python_graph,
        select=request.select,
        exclude=request.exclude,
    )
    required_refs: frozenset[SqlResourceRef] = python_graph.selected_sql_refs(
        selected_names=check_names
    )
    dependency_names: frozenset[str] = check_dependency_closure(
        graph=python_graph, check_names=check_names
    )
    required_loader_names: frozenset[str] = frozenset(
        name
        for name in dependency_names
        if python_graph.nodes_by_name[name].kind == PythonNodeKind.LOADER
    )
    required_source_names: frozenset[str] = _required_loader_source_names(
        invocation=invocation,
        required_loader_names=required_loader_names,
    )
    selected_keys: frozenset[CompiledObjectKey] = frozenset(
        CompiledObjectKey(
            resource_type=(
                CompiledResourceType.MODEL
                if ref.kind == SqlResourceRefKind.MODEL
                else CompiledResourceType.SOURCE
            ),
            name=ref.name,
        )
        for ref in required_refs
        if ref.kind in {SqlResourceRefKind.MODEL, SqlResourceRefKind.SOURCE}
    ) | frozenset(
        CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name)
        for name in required_source_names
    )
    context: StaticCommandContext = compile_static_command_context(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        options=CompilePipelineOptions(
            selected_target=request.selected_target,
            no_sql_validation=request.no_sql_validation,
            source_deferral_enabled=False,
            connection_config=invocation.connection_config,
            cli_vars=request.cli_vars,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=invocation.effective_project_dir,
                discovered_inputs=invocation.discovered_inputs,
            ),
        ),
        selected_keys=selected_keys,
        relation_keys=selected_keys,
        on_progress=invocation.planning_progress.on_progress,
    )
    return build_static_pipeline_result(
        context=context,
        plan_output=build_relation_command_plan(
            project=context.project,
            scope=context.scope,
            relations=context.relations,
        ),
    )


def _required_loader_source_names(
    *, invocation: CheckInvocation, required_loader_names: frozenset[str]
) -> frozenset[str]:
    names: set[str] = set()
    for source_file in invocation.discovered_inputs.source_files:
        for source in source_file.source_entries:
            if source.loader in required_loader_names:
                names.add(source.name)
    return frozenset(names)
