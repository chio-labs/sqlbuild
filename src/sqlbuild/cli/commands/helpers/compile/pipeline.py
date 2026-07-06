"""Compile pipeline phases: analysis, manifest, DAG, and artifact writing."""

from __future__ import annotations

import time
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.compile.dag import resolve_compile_dag_path
from sqlbuild.cli.commands.helpers.compile.lineage import (
    build_compile_lineage,
    compile_analysis_lineage_mode,
)
from sqlbuild.cli.commands.helpers.compile.models import (
    CompileAnalysis,
    CompileWriteResult,
    WrittenTarget,
)
from sqlbuild.cli.commands.helpers.compile.status import (
    complete_compile_phase,
    elapsed_ms,
    start_compile_phase,
)
from sqlbuild.cli.commands.helpers.compile.target_writer import write_static_compile_target
from sqlbuild.cli.commands.helpers.compile.types import CompileLineageMode
from sqlbuild.cli.commands.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.compiler.compile.main.load_macros import load_macros
from sqlbuild.compiler.compile.models.core import LoadedMacro
from sqlbuild.compiler.contracts.main.validate import validate_model_contracts
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.dag.main.build import build_dag_json
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.manifest.main.build import build_manifest
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.shared.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def analyze_compile_project(
    *,
    project_dir: Path,
    no_sql_validation: bool,
    selected_target: str | None,
    lineage_mode: CompileLineageMode,
    cli_vars: dict[str, object] | None,
    profile_skip_discovery_sql_analysis: bool,
    profile_skip_column_inference: bool,
    profile_skip_contracts: bool,
    status: TransientStatusReporter | None,
) -> CompileAnalysis:
    """Discover, compile, and validate the project into one analysis result."""

    discover_start: float = time.monotonic()
    _ = start_compile_phase(status, "Discovering project...")
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=project_dir,
        sql_analysis_enabled_override=False if profile_skip_discovery_sql_analysis else None,
    )
    discover_ms: int = elapsed_ms(discover_start)
    _ = complete_compile_phase(status, f"Discovered project. ({discover_ms / 1000:.2f}s)")
    adapter: BaseAdapter = resolve_adapter(
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=project_dir,
    )
    graph_start: float = time.monotonic()
    _ = start_compile_phase(status, "Compiling project graph...")
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=selected_target,
        no_sql_validation=no_sql_validation,
        skip_column_inference=profile_skip_column_inference,
        column_lineage_mode=compile_analysis_lineage_mode(lineage_mode),
        cli_vars=cli_vars,
    )
    graph_ms: int = elapsed_ms(graph_start)
    _ = complete_compile_phase(status, f"Compiled project graph. ({graph_ms / 1000:.2f}s)")
    lineage_start: float = time.monotonic()
    _ = start_compile_phase(status, "Analyzing column lineage...")
    lineage: ProjectColumnLineage | None = build_compile_lineage(
        graph=graph,
        dialect=adapter.sql_analysis_dialect(),
        mode=lineage_mode,
    )
    lineage_ms: int = elapsed_ms(lineage_start)
    _ = complete_compile_phase(status, f"Analyzed column lineage. ({lineage_ms / 1000:.2f}s)")
    contracts_start: float = time.monotonic()
    contract_result: ContractValidationResult
    if profile_skip_contracts:
        contract_result = ContractValidationResult(diagnostics=())
    else:
        _ = start_compile_phase(status, "Validating model contracts...")
        contract_result = validate_model_contracts(
            graph.project,
            dialect=adapter.sql_analysis_dialect(),
        )
    contract_ms: int = elapsed_ms(contracts_start)
    if not profile_skip_contracts:
        _ = complete_compile_phase(
            status, f"Validated model contracts. ({contract_ms / 1000:.2f}s)"
        )
    return CompileAnalysis(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        graph=graph,
        lineage=lineage,
        diagnostics=(*graph.project.diagnostics, *contract_result.diagnostics),
        discover_ms=discover_ms,
        graph_ms=graph_ms,
        lineage_ms=lineage_ms,
        contract_ms=contract_ms,
    )


def build_compile_manifest_payload(
    *,
    manifest: bool,
    analysis: CompileAnalysis,
    status: TransientStatusReporter | None,
) -> dict[str, object] | None:
    """Build the manifest payload when requested."""

    if not manifest:
        return None
    manifest_start: float = time.monotonic()
    _ = start_compile_phase(status, "Building manifest...")
    loaded_macros: dict[str, LoadedMacro] = load_macros(analysis.discovered_inputs.macro_files)
    manifest_payload: dict[str, object] = build_manifest(
        project=analysis.graph.project,
        loaded_macros=loaded_macros,
        project_name=analysis.discovered_inputs.project_config.name,
        adapter_type=resolve_effective_adapter_name(
            project_config=analysis.discovered_inputs.project_config,
            local_config=analysis.discovered_inputs.local_config,
        ),
        upstream_deps=analysis.graph.upstream_deps,
        downstream_deps=analysis.graph.downstream_deps,
    )
    _ = complete_compile_phase(
        status, f"Built manifest. ({time.monotonic() - manifest_start:.2f}s)"
    )
    return manifest_payload


def write_compile_dag_artifact(
    *,
    dag_path: str | None,
    project_dir: Path,
    analysis: CompileAnalysis,
    status: TransientStatusReporter | None,
) -> None:
    """Write the DAG JSON artifact when a DAG path is requested."""

    if dag_path is None:
        return
    dag_start: float = time.monotonic()
    _ = start_compile_phase(status, "Writing DAG artifact...")
    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=analysis.discovered_inputs
    )
    resolved_dag_path: Path = resolve_compile_dag_path(
        project_dir=project_dir,
        dag_path=dag_path,
    )
    resolved_dag_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_dag_path.write_text(
        build_dag_json(
            graph=analysis.graph,
            project_name=analysis.discovered_inputs.project_config.name,
            python_graph=python_graph,
        ),
        encoding="utf-8",
    )
    _ = complete_compile_phase(status, f"Wrote DAG artifact. ({time.monotonic() - dag_start:.2f}s)")


def write_compile_artifacts(
    *,
    profile_skip_write: bool,
    project_dir: Path,
    analysis: CompileAnalysis,
    manifest_payload: dict[str, object] | None,
    status: TransientStatusReporter | None,
) -> CompileWriteResult:
    """Write compiled artifacts to target/ and report the written counts."""

    write_start: float = time.monotonic()
    target_dir: Path = project_dir / "target"
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
        _ = start_compile_phase(status, "Writing compiled artifacts...")
        written = write_static_compile_target(
            target_dir=target_dir,
            adapter=analysis.adapter,
            project=analysis.graph.project,
            manifest=manifest_payload,
        )
    write_ms: int = elapsed_ms(write_start)
    if not profile_skip_write:
        _ = complete_compile_phase(status, f"Wrote compiled artifacts. ({write_ms / 1000:.2f}s)")
    return CompileWriteResult(written=written, write_ms=write_ms)
