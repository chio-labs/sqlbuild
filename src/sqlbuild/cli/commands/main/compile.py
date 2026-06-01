"""CLI compile command entry point."""

from __future__ import annotations

import time
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.compile.constants import (
    RICH_LINEAGE_STATUS_MODEL_THRESHOLD,
)
from sqlbuild.cli.commands.main.helpers.compile.dag import resolve_compile_dag_path
from sqlbuild.cli.commands.main.helpers.compile.models import WrittenTarget
from sqlbuild.cli.commands.main.helpers.compile.output import (
    format_compile_json,
    format_compile_text,
)
from sqlbuild.cli.commands.main.helpers.compile.target_writer import write_static_compile_target
from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.status import maybe_status
from sqlbuild.compiler.compile.main.load_macros import load_macros
from sqlbuild.compiler.compile.models.core import LoadedMacro
from sqlbuild.compiler.contracts.main.validate import validate_model_contracts
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.dag.main.build import build_dag_json
from sqlbuild.compiler.diagnostics.models import CompilerDiagnostic
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.main.columns import build_project_column_lineage
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.manifest.main.build import build_manifest
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_compile(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    json_output: bool = False,
    manifest: bool = False,
    dag_path: str | None = None,
    no_color: bool = False,
    lineage_mode: CompileLineageMode = CompileLineageMode.FAST,
    cli_vars: dict[str, object] | None = None,
) -> int:
    """Execute the compile command."""

    del defer_to
    total_start: float = time.monotonic()
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discover_start: float = time.monotonic()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    discover_ms: int = _elapsed_ms(discover_start)
    adapter: BaseAdapter = resolve_adapter(
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=effective_project_dir,
    )
    graph_start: float = time.monotonic()
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
    )
    graph_ms: int = _elapsed_ms(graph_start)
    lineage_start: float = time.monotonic()
    lineage: ProjectColumnLineage | None = _build_compile_lineage(
        graph=graph,
        dialect=adapter.sqlglot_dialect(),
        mode=lineage_mode,
    )
    lineage_ms: int = _elapsed_ms(lineage_start)
    contracts_start: float = time.monotonic()
    contract_result: ContractValidationResult = validate_model_contracts(
        graph.project,
        dialect=adapter.sqlglot_dialect(),
    )
    contract_ms: int = _elapsed_ms(contracts_start)
    diagnostics: tuple[CompilerDiagnostic, ...] = (
        *graph.project.diagnostics,
        *contract_result.diagnostics,
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
    if dag_path is not None:
        python_graph: PythonNodeGraph = build_discovered_python_node_graph(
            discovered_inputs=discovered_inputs
        )
        resolved_dag_path: Path = resolve_compile_dag_path(
            project_dir=effective_project_dir,
            dag_path=dag_path,
        )
        resolved_dag_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_dag_path.write_text(
            build_dag_json(
                graph=graph,
                project_name=discovered_inputs.project_config.name,
                python_graph=python_graph,
            ),
            encoding="utf-8",
        )

    write_start: float = time.monotonic()
    written: WrittenTarget = write_static_compile_target(
        target_dir=effective_project_dir / "target",
        adapter=adapter,
        project=graph.project,
        manifest=manifest_payload,
    )
    write_ms: int = _elapsed_ms(write_start)
    timings_ms: dict[str, int] = {
        "discover_ms": discover_ms,
        "graph_ms": graph_ms,
        "lineage_ms": lineage_ms,
        "contracts_ms": contract_ms,
        "write_ms": write_ms,
        "total_ms": _elapsed_ms(total_start),
    }
    exit_code: int = 1 if any(diagnostic.is_error for diagnostic in diagnostics) else 0

    if json_output:
        print(
            format_compile_json(
                graph=graph,
                written=written,
                manifest=manifest,
                timings_ms=timings_ms,
                lineage=lineage,
                lineage_mode=lineage_mode,
                diagnostics=diagnostics,
            )
        )
        return exit_code

    print(
        format_compile_text(
            graph=graph,
            written=written,
            manifest=manifest,
            lineage=lineage,
            lineage_mode=lineage_mode,
            diagnostics=diagnostics,
            use_color=(not no_color) and supports_color(),
        )
    )
    return exit_code


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _build_compile_lineage(
    *,
    graph: ProjectGraph,
    dialect: str | None,
    mode: CompileLineageMode,
) -> ProjectColumnLineage | None:
    match mode:
        case CompileLineageMode.NONE:
            return None
        case CompileLineageMode.FAST:
            return build_project_column_lineage(
                graph.project,
                dialect=dialect,
                mode=ColumnLineageMode.FAST,
            )
        case CompileLineageMode.RICH:
            model_count: int = len(graph.project.models)
            with maybe_status(
                f"Analyzing rich column lineage for {model_count} models...",
                enabled=model_count >= RICH_LINEAGE_STATUS_MODEL_THRESHOLD,
            ):
                return build_project_column_lineage(
                    graph.project,
                    dialect=dialect,
                    mode=ColumnLineageMode.RICH,
                )
