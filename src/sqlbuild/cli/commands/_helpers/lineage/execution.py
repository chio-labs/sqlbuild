"""Lineage command preparation, selection, and rendering."""

from __future__ import annotations

import json
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.lineage.cache import (
    read_relation_lineage_cache,
    relation_lineage_fingerprint,
    write_relation_lineage_cache,
)
from sqlbuild.cli.commands._helpers.lineage.output import (
    format_column_lineage_json,
    format_column_lineage_list,
    format_column_lineage_tree,
    format_lineage_json,
    format_lineage_list,
    format_lineage_tree,
)
from sqlbuild.cli.commands._helpers.lineage.selection import (
    parse_depth,
    select_column_target_lineage,
    select_selector_lineage,
    select_target_lineage,
)
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands.constants import (
    COLUMN_TARGET_SEPARATOR,
    JSON_OUTPUT_FORMAT,
    LIST_OUTPUT_FORMAT,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    ColumnLineageTrace,
    LineageCommandRequest,
    LineageGraph,
    RelationLineageIndex,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.main.build_semantic_uses import build_direct_semantic_uses
from sqlbuild.compiler.lineage.models import DirectSemanticColumnUse
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def execute_lineage(*, request: LineageCommandRequest) -> int:
    """Execute a validated lineage request through focused phases."""

    _validate_request(request=request)
    graph, adapter, parsed_depth = _prepare_graph(request=request)
    uses: tuple[DirectSemanticColumnUse, ...] = _semantic_uses(
        request=request, graph=graph, adapter=adapter
    )
    rendered: str = _render_lineage(request=request, graph=graph, parsed_depth=parsed_depth)
    _write_lineage(
        rendered=rendered,
        output_format=request.output_format,
        uses=uses,
        include_uses=request.include_uses,
    )
    return 0


def _validate_request(*, request: LineageCommandRequest) -> None:
    if request.target is not None and request.select:
        raise CliUserError("lineage accepts either a target or --select, not both", code="C301")
    if request.target is None and not request.select:
        raise CliUserError("lineage requires a target or --select", code="C302")
    if request.exclude and not request.select:
        raise CliUserError("--exclude can only be used with --select", code="C303")


def _prepare_graph(
    *, request: LineageCommandRequest
) -> tuple[ProjectGraph | RelationLineageIndex, BaseAdapter | None, int | None]:
    parsed_depth: int | None = parse_depth(request.depth)
    project_dir: Path = request.project_dir or Path.cwd()
    requires_compiled_graph: bool = _requires_compiled_graph(request=request)
    fingerprint: str | None = (
        None
        if requires_compiled_graph
        else relation_lineage_fingerprint(project_dir=project_dir, cli_vars=request.cli_vars)
    )
    if fingerprint is not None:
        cached: RelationLineageIndex | None = read_relation_lineage_cache(
            project_dir=project_dir,
            fingerprint=fingerprint,
        )
        if cached is not None:
            return cached, None, parsed_depth
    discovered: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=project_dir,
        sql_analysis_enabled_override=(None if requires_compiled_graph else False),
        extract_output_column_locations=False,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered.project_config,
            local_config=discovered.local_config,
        ),
        project_dir=project_dir,
    )
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered,
        adapter=adapter,
        no_sql_validation=request.no_sql_validation or not requires_compiled_graph,
        skip_column_inference=not requires_compiled_graph,
        cli_vars=request.cli_vars,
    )
    if fingerprint is not None:
        return (
            write_relation_lineage_cache(
                project_dir=project_dir,
                fingerprint=fingerprint,
                graph=graph,
            ),
            None,
            parsed_depth,
        )
    return graph, adapter, parsed_depth


def _requires_compiled_graph(*, request: LineageCommandRequest) -> bool:
    return request.include_uses or (
        request.target is not None and COLUMN_TARGET_SEPARATOR in request.target
    )


def _semantic_uses(
    *,
    request: LineageCommandRequest,
    graph: ProjectGraph | RelationLineageIndex,
    adapter: BaseAdapter | None,
) -> tuple[DirectSemanticColumnUse, ...]:
    if not request.include_uses:
        return ()
    if not isinstance(graph, ProjectGraph) or adapter is None:
        raise CliUserError(
            "semantic uses require a compiled project graph",
            code="C307",
        )
    return build_direct_semantic_uses(
        project=graph.project,
        dialect=adapter.sql_analysis_dialect(),
        model_names=_semantic_use_model_names(request=request, graph=graph),
    )


def _render_lineage(
    *,
    request: LineageCommandRequest,
    graph: ProjectGraph | RelationLineageIndex,
    parsed_depth: int | None,
) -> str:
    if request.target is not None:
        column_trace: ColumnLineageTrace | None = select_column_target_lineage(
            graph=graph,
            target=request.target,
            direction=request.direction,
            depth=parsed_depth,
            mode=request.lineage_mode,
        )
        if column_trace is not None:
            return _format_column_trace(trace=column_trace, output_format=request.output_format)
        lineage_graph: LineageGraph = select_target_lineage(
            graph=graph,
            target=request.target,
            direction=request.direction,
            depth=parsed_depth,
        )
    else:
        lineage_graph = select_selector_lineage(
            graph=graph,
            select=request.select,
            exclude=request.exclude,
            depth=parsed_depth,
        )
    return _format_graph(graph=lineage_graph, output_format=request.output_format)


def _format_column_trace(*, trace: ColumnLineageTrace, output_format: str) -> str:
    if output_format == JSON_OUTPUT_FORMAT:
        return format_column_lineage_json(trace)
    if output_format == LIST_OUTPUT_FORMAT:
        return format_column_lineage_list(trace=trace, use_color=supports_color())
    return format_column_lineage_tree(trace=trace, use_color=supports_color())


def _format_graph(*, graph: LineageGraph, output_format: str) -> str:
    if output_format == JSON_OUTPUT_FORMAT:
        return format_lineage_json(graph)
    if output_format == LIST_OUTPUT_FORMAT:
        return format_lineage_list(graph=graph, use_color=supports_color())
    return format_lineage_tree(graph=graph, use_color=supports_color())


def _semantic_use_model_names(
    *, request: LineageCommandRequest, graph: ProjectGraph
) -> frozenset[str]:
    if request.target is not None:
        return frozenset({request.target.split(".", maxsplit=1)[0]})
    keys: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=request.select,
        exclude=request.exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    return frozenset(key.name for key in keys if key.resource_type == CompiledResourceType.MODEL)


def _write_lineage(
    *,
    rendered: str,
    output_format: str,
    uses: tuple[DirectSemanticColumnUse, ...],
    include_uses: bool,
) -> None:
    if not include_uses:
        print(rendered if output_format == JSON_OUTPUT_FORMAT else f"\n{rendered}\n")
        return
    if output_format == JSON_OUTPUT_FORMAT:
        payload: dict[str, object] = json.loads(rendered)
        payload["semantic_uses"] = [_serialize_use(use=use) for use in uses]
        print(json.dumps(payload, indent=2))
        return
    lines: list[str] = ["", rendered, "", "Direct semantic column uses"]
    if not uses:
        lines.append("  none")
    else:
        lines.extend(
            f"  {use.consumer_model} [{use.context}] "
            f"{use.source.resource_type}:{use.source.resource_name}.{use.source.column_name} "
            f"<- {use.expression_sql}"
            for use in uses
        )
    print("\n".join(lines) + "\n")


def _serialize_use(*, use: DirectSemanticColumnUse) -> dict[str, object]:
    return {
        "consumer_model": use.consumer_model,
        "context": use.context,
        "expression": use.expression_sql,
        "source": {
            "resource_type": str(use.source.resource_type),
            "resource_name": use.source.resource_name,
            "column": use.source.column_name,
        },
        "confidence": use.confidence.value,
        "line": use.line,
        "column": use.column,
    }
