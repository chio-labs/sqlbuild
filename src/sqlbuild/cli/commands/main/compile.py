"""CLI compile command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.compile.models import WrittenTarget
from sqlbuild.cli.commands.main.helpers.compile.target_writer import write_static_compile_target
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.json_output import format_static_compile_json
from sqlbuild.compiler.compile.main.load_macros import load_macros
from sqlbuild.compiler.compile.models import LoadedMacro
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.manifest.main.build import build_manifest
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_compile(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    json_output: bool = False,
    manifest: bool = False,
) -> int:
    """Execute the compile command."""

    del defer_to
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
    manifest_payload: dict[str, object] | None = None
    if manifest:
        loaded_macros: dict[str, LoadedMacro] = load_macros(discovered_inputs.macro_files)
        manifest_payload = build_manifest(
            project=graph.project,
            loaded_macros=loaded_macros,
            project_name=discovered_inputs.project_config.name,
            adapter_type=resolve_effective_adapter_name(
                project_config=discovered_inputs.project_config,
                local_config=discovered_inputs.local_config,
            ),
            upstream_deps=graph.upstream_deps,
            downstream_deps=graph.downstream_deps,
        )

    written: WrittenTarget = write_static_compile_target(
        target_dir=effective_project_dir / "target",
        adapter=adapter,
        project=graph.project,
        manifest=manifest_payload,
    )

    if json_output:
        print(format_static_compile_json(graph))
        return 0

    _print_summary(written=written, manifest=manifest)
    return 0


def _print_summary(*, written: WrittenTarget, manifest: bool) -> None:
    """Print compile output summary."""

    print(written.summary_line())
    print()
    print(f"{'target/compiled/':20s} resolved SQL")
    if manifest:
        print("target/manifest.json")
