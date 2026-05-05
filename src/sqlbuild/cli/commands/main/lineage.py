"""CLI lineage command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.lineage.models import LineageGraph
from sqlbuild.cli.commands.main.helpers.lineage.output import (
    format_lineage_json,
    format_lineage_list,
    format_lineage_tree,
)
from sqlbuild.cli.commands.main.helpers.lineage.selection import (
    parse_depth,
    select_selector_lineage,
    select_target_lineage,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_lineage(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    target: str | None = None,
    output_format: str = "tree",
    direction: str = "upstream",
    depth: str = "all",
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> int:
    """Execute the lineage command."""

    if target is not None and select:
        raise CliUserError("lineage accepts either a target or --select, not both")
    if target is None and not select:
        raise CliUserError("lineage requires a target or --select")
    if exclude and not select:
        raise CliUserError("--exclude can only be used with --select")

    parsed_depth: int | None = parse_depth(depth)
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=effective_project_dir,
    )
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
    )
    lineage_graph: LineageGraph
    if target is not None:
        lineage_graph = select_target_lineage(
            graph=graph,
            target=target,
            direction=direction,
            depth=parsed_depth,
        )
    else:
        lineage_graph = select_selector_lineage(
            graph=graph,
            select=select,
            exclude=exclude,
            depth=parsed_depth,
        )

    if output_format == "json":
        print(format_lineage_json(lineage_graph))
    elif output_format == "list":
        print("\n" + format_lineage_list(lineage_graph, use_color=supports_color()) + "\n")
    else:
        print("\n" + format_lineage_tree(lineage_graph, use_color=supports_color()) + "\n")
    return 0
