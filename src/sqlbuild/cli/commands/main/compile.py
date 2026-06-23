"""CLI compile command entry point."""

from __future__ import annotations

import time
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.compile.dag import resolve_compile_dag_path
from sqlbuild.cli.commands.main.helpers.compile.lineage import (
    build_compile_lineage,
    compile_analysis_lineage_mode,
)
from sqlbuild.cli.commands.main.helpers.compile.models import WrittenTarget
from sqlbuild.cli.commands.main.helpers.compile.output import (
    format_compile_json,
    format_compile_text,
)
from sqlbuild.cli.commands.main.helpers.compile.status import (
    complete_compile_phase,
    elapsed_ms,
    start_compile_phase,
    start_compile_status,
)
from sqlbuild.cli.commands.main.helpers.compile.target_writer import write_static_compile_target
from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode
from sqlbuild.cli.commands.main.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.compiler.compile.main.load_macros import load_macros
from sqlbuild.compiler.compile.models.core import LoadedMacro
from sqlbuild.compiler.contracts.main.validate import validate_model_contracts
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.dag.main.build import build_dag_json
from sqlbuild.compiler.diagnostics.models import CompilerDiagnostic
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.manifest.main.build import build_manifest
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.shared.helpers.status import TransientStatusReporter
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
    profile_skip_discovery_sql_analysis: bool = False,
    profile_skip_column_inference: bool = False,
    profile_skip_contracts: bool = False,
    profile_skip_write: bool = False,
) -> int:
    """Execute the compile command."""

    del defer_to
    total_start: float = time.monotonic()
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    status: TransientStatusReporter | None = start_compile_status(
        json_output=json_output,
        no_color=no_color,
    )
    try:
        return _run_compile_with_status(
            project_dir=effective_project_dir,
            no_sql_validation=no_sql_validation,
            json_output=json_output,
            manifest=manifest,
            dag_path=dag_path,
            no_color=no_color,
            lineage_mode=lineage_mode,
            cli_vars=cli_vars,
            profile_skip_discovery_sql_analysis=profile_skip_discovery_sql_analysis,
            profile_skip_column_inference=profile_skip_column_inference,
            profile_skip_contracts=profile_skip_contracts,
            profile_skip_write=profile_skip_write,
            total_start=total_start,
            status=status,
        )
    finally:
        if status is not None:
            status.close()


def _run_compile_with_status(
    *,
    project_dir: Path,
    no_sql_validation: bool,
    json_output: bool,
    manifest: bool,
    dag_path: str | None,
    no_color: bool,
    lineage_mode: CompileLineageMode,
    cli_vars: dict[str, object] | None,
    profile_skip_discovery_sql_analysis: bool,
    profile_skip_column_inference: bool,
    profile_skip_contracts: bool,
    profile_skip_write: bool,
    total_start: float,
    status: TransientStatusReporter | None,
) -> int:
    """Execute compile after the optional interactive status reporter is initialized."""

    effective_project_dir: Path = project_dir
    discover_start: float = time.monotonic()
    start_compile_phase(status, "Discovering project...")
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir,
        sql_analysis_enabled_override=False if profile_skip_discovery_sql_analysis else None,
    )
    discover_ms: int = elapsed_ms(discover_start)
    complete_compile_phase(status, f"Discovered project. ({discover_ms / 1000:.2f}s)")
    adapter: BaseAdapter = resolve_adapter(
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=effective_project_dir,
    )
    graph_start: float = time.monotonic()
    start_compile_phase(status, "Compiling project graph...")
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        skip_column_inference=profile_skip_column_inference,
        column_lineage_mode=compile_analysis_lineage_mode(lineage_mode),
        cli_vars=cli_vars,
    )
    graph_ms: int = elapsed_ms(graph_start)
    complete_compile_phase(status, f"Compiled project graph. ({graph_ms / 1000:.2f}s)")
    lineage_start: float = time.monotonic()
    start_compile_phase(status, "Analyzing column lineage...")
    lineage: ProjectColumnLineage | None = build_compile_lineage(
        graph=graph,
        dialect=adapter.sql_analysis_dialect(),
        mode=lineage_mode,
    )
    lineage_ms: int = elapsed_ms(lineage_start)
    complete_compile_phase(status, f"Analyzed column lineage. ({lineage_ms / 1000:.2f}s)")
    contracts_start: float = time.monotonic()
    contract_result: ContractValidationResult
    if profile_skip_contracts:
        contract_result = ContractValidationResult(diagnostics=())
    else:
        start_compile_phase(status, "Validating model contracts...")
        contract_result = validate_model_contracts(
            graph.project,
            dialect=adapter.sql_analysis_dialect(),
        )
    contract_ms: int = elapsed_ms(contracts_start)
    if not profile_skip_contracts:
        complete_compile_phase(status, f"Validated model contracts. ({contract_ms / 1000:.2f}s)")
    diagnostics: tuple[CompilerDiagnostic, ...] = (
        *graph.project.diagnostics,
        *contract_result.diagnostics,
    )
    manifest_payload: dict[str, object] | None = None
    if manifest:
        manifest_start: float = time.monotonic()
        start_compile_phase(status, "Building manifest...")
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
        complete_compile_phase(
            status, f"Built manifest. ({time.monotonic() - manifest_start:.2f}s)"
        )
    if dag_path is not None:
        dag_start: float = time.monotonic()
        start_compile_phase(status, "Writing DAG artifact...")
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
        complete_compile_phase(status, f"Wrote DAG artifact. ({time.monotonic() - dag_start:.2f}s)")

    write_start: float = time.monotonic()
    target_dir: Path = effective_project_dir / "target"
    written: WrittenTarget
    if profile_skip_write:
        written = WrittenTarget(
            model_count=0,
            seed_count=0,
            function_count=0,
            audit_count=0,
            test_count=0,
            target_dir=target_dir,
        )
    else:
        start_compile_phase(status, "Writing compiled artifacts...")
        written = write_static_compile_target(
            target_dir=target_dir,
            adapter=adapter,
            project=graph.project,
            manifest=manifest_payload,
        )
    write_ms: int = elapsed_ms(write_start)
    if not profile_skip_write:
        complete_compile_phase(status, f"Wrote compiled artifacts. ({write_ms / 1000:.2f}s)")
    timings_ms: dict[str, int] = {
        "discover_ms": discover_ms,
        "graph_ms": graph_ms,
        "lineage_ms": lineage_ms,
        "contracts_ms": contract_ms,
        "write_ms": write_ms,
        "total_ms": elapsed_ms(total_start),
    }
    exit_code: int = 1 if any(diagnostic.is_error for diagnostic in diagnostics) else 0

    if status is not None:
        status.close()

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
