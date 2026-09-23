"""Compile pipeline phases: analysis, manifest, DAG, and artifact writing."""

from __future__ import annotations

import time
from dataclasses import replace
from functools import partial
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.compile.lineage import (
    build_compile_lineage,
    compile_analysis_lineage_mode,
)
from sqlbuild.cli.commands._helpers.compile.status import (
    complete_compile_phase,
    elapsed_ms,
    start_compile_phase,
)
from sqlbuild.cli.commands._helpers.compile.target_writer import write_static_compile_target
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands.classes.prepared_compile_artifacts import PreparedCompileArtifacts
from sqlbuild.cli.commands.types import CompileLineageMode
from sqlbuild.cli.compile.models import (
    CompileAnalysis,
    CompileProfileFlags,
    CompileWriteResult,
)
from sqlbuild.cli.output.models import (
    WrittenTarget,
)
from sqlbuild.compiler.compile.models import (
    CompileAnalysisSelection,
    CompiledObjectKey,
    CompilerDiagnostic,
)
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.contracts.main.validate import evaluate_model_contracts
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.pipeline.main.selected_graph import (
    build_project_graph_with_analysis_selection,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.rule_engine.classes.early_sql_lint import EarlySqlLint
from sqlbuild.rule_engine.main.load_config import load_rules_config
from sqlbuild.rule_engine.main.run_rules import run_rules
from sqlbuild.rule_engine.models import RulesConfig, RulesRunResult
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def analyze_compile_project(
    *,
    project_dir: Path,
    no_sql_validation: bool,
    selected_target: str | None,
    lineage_mode: CompileLineageMode,
    cli_vars: dict[str, object] | None,
    profile_flags: CompileProfileFlags,
    analysis_selection: CompileAnalysisSelection,
    status: TransientStatusReporter | None,
    prepared_artifacts: PreparedCompileArtifacts | None = None,
) -> CompileAnalysis:
    """Discover, compile, and validate the project into one analysis result."""

    with EarlySqlLint(
        enabled=not (analysis_selection.select or analysis_selection.exclude)
    ) as early_lint:
        return _analyze_compile_project(
            project_dir=project_dir,
            no_sql_validation=no_sql_validation,
            selected_target=selected_target,
            lineage_mode=lineage_mode,
            cli_vars=cli_vars,
            profile_flags=profile_flags,
            analysis_selection=analysis_selection,
            status=status,
            early_lint=early_lint,
            prepared_artifacts=prepared_artifacts,
        )


def _analyze_compile_project(
    *,
    project_dir: Path,
    no_sql_validation: bool,
    selected_target: str | None,
    lineage_mode: CompileLineageMode,
    cli_vars: dict[str, object] | None,
    profile_flags: CompileProfileFlags,
    analysis_selection: CompileAnalysisSelection,
    status: TransientStatusReporter | None,
    early_lint: EarlySqlLint,
    prepared_artifacts: PreparedCompileArtifacts | None = None,
) -> CompileAnalysis:
    select: tuple[str, ...] = analysis_selection.select
    exclude: tuple[str, ...] = analysis_selection.exclude

    discover_start: float = time.monotonic()
    _ = start_compile_phase(status=status, message="Discovering project...")
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=project_dir,
        extract_output_column_locations=False,
        sql_analysis_enabled_override=(
            False if profile_flags.skip_discovery_sql_analysis else None
        ),
    )
    discover_ms: int = elapsed_ms(discover_start)
    _ = complete_compile_phase(
        status=status, message=f"Discovered project. ({discover_ms / 1000:.2f}s)"
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=project_dir,
    )
    graph_start: float = time.monotonic()
    _ = start_compile_phase(status=status, message="Compiling project graph...")
    with OperationLifecycle(operation_kind="project", operation_name="project_compile"):
        graph: ProjectGraph = build_project_graph_with_analysis_selection(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            selected_target=selected_target,
            no_sql_validation=no_sql_validation,
            skip_column_inference=profile_flags.skip_column_inference,
            column_lineage_mode=compile_analysis_lineage_mode(lineage_mode),
            cli_vars=cli_vars,
            analysis_selection=replace(
                analysis_selection,
                on_inputs_ready=partial(
                    early_lint.start, dialect=adapter.sql_analysis_dialect() or "generic"
                ),
            ),
        )
    graph_ms: int = elapsed_ms(graph_start)
    _ = complete_compile_phase(
        status=status, message=f"Compiled project graph. ({graph_ms / 1000:.2f}s)"
    )
    lineage_start: float = time.monotonic()
    _ = start_compile_phase(status=status, message="Analyzing column lineage...")
    lineage: ProjectColumnLineage | None = build_compile_lineage(
        graph=graph,
        dialect=adapter.sql_analysis_dialect(),
        mode=lineage_mode,
    )
    lineage_ms: int = elapsed_ms(lineage_start)
    _ = complete_compile_phase(
        status=status, message=f"Analyzed column lineage. ({lineage_ms / 1000:.2f}s)"
    )
    contracts_start: float = time.monotonic()
    contract_result: ContractValidationResult
    if profile_flags.skip_contracts:
        contract_result = ContractValidationResult(diagnostics=())
    else:
        _ = start_compile_phase(status=status, message="Validating model contracts...")
        contract_result = evaluate_model_contracts(
            project=graph.project,
            dialect=adapter.sql_analysis_dialect(),
        )
    contract_ms: int = elapsed_ms(contracts_start)
    if not profile_flags.skip_contracts:
        _ = complete_compile_phase(
            status=status, message=f"Validated model contracts. ({contract_ms / 1000:.2f}s)"
        )
    selected_keys: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=select,
        exclude=exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    rules_result: RulesRunResult = RulesRunResult(
        findings=(), evaluated_models=0, built_in_ms=0, custom_ms=0
    )
    core_diagnostics: tuple[CompilerDiagnostic, ...] = (
        *graph.project.diagnostics,
        *contract_result.diagnostics,
    )
    if not any(diagnostic.is_error for diagnostic in graph.project.diagnostics):
        rules_config: RulesConfig = load_rules_config(project_dir=project_dir)
        if (
            prepared_artifacts is not None
            and rules_config.select
            and not any(item.is_error for item in core_diagnostics)
        ):
            prepared_artifacts.start(project=graph.project, adapter=adapter)
        _ = start_compile_phase(status=status, message="Evaluating built-in and custom rules...")
        rules_result = run_rules(
            graph=graph,
            discovered_inputs=discovered_inputs,
            config=rules_config,
            project_dir=project_dir,
            dialect=adapter.sql_analysis_dialect() or "generic",
            selected_keys=selected_keys if select or exclude else None,
            prepared_sql=early_lint.preparation,
            expansion_reuse=early_lint.expansion_reuse,
        )
        _ = complete_compile_phase(
            status=status,
            message=(
                f"Evaluated rules. (built-in {rules_result.built_in_ms / 1000:.2f}s, "
                f"custom {rules_result.custom_ms / 1000:.2f}s)"
            ),
        )
    rule_diagnostics: tuple[CompilerDiagnostic, ...] = tuple(
        CompilerDiagnostic(
            phase=DiagnosticPhase.RULE,
            severity=DiagnosticSeverity.ERROR,
            code=fault.code,
            message=fault.message,
            path=fault.path,
            line=fault.line,
            column=fault.column,
            help=fault.remediation,
        )
        for fault in rules_result.findings
    )
    return CompileAnalysis(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        graph=graph,
        selected_keys=selected_keys,
        lineage=lineage,
        diagnostics=(*core_diagnostics, *rule_diagnostics),
        discover_ms=discover_ms,
        graph_ms=graph_ms,
        lineage_ms=lineage_ms,
        contract_ms=contract_ms,
        built_in_rules_ms=rules_result.built_in_ms,
        custom_rules_ms=rules_result.custom_ms,
        rule_cache_hits=rules_result.cache_hits,
        rule_cache_misses=rules_result.cache_misses,
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
    from sqlbuild.compiler.manifest.main.build import build_manifest

    manifest_start: float = time.monotonic()
    _ = start_compile_phase(status=status, message="Building manifest...")
    manifest_payload: dict[str, object] = build_manifest(
        project=analysis.graph.project,
        project_name=analysis.discovered_inputs.project_config.name,
        adapter_type=resolve_effective_adapter_name(
            project_config=analysis.discovered_inputs.project_config,
            local_config=analysis.discovered_inputs.local_config,
        ),
        upstream_deps=analysis.graph.upstream_deps,
        downstream_deps=analysis.graph.downstream_deps,
    )
    _ = complete_compile_phase(
        status=status, message=f"Built manifest. ({time.monotonic() - manifest_start:.2f}s)"
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
    from sqlbuild.cli.commands._helpers.compile.dag import resolve_compile_dag_path
    from sqlbuild.compiler.dag.main.build import build_dag_json
    from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
    from sqlbuild.compiler.python_nodes.models import PythonNodeGraph

    dag_start: float = time.monotonic()
    _ = start_compile_phase(status=status, message="Writing DAG artifact...")
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
    _ = complete_compile_phase(
        status=status, message=f"Wrote DAG artifact. ({time.monotonic() - dag_start:.2f}s)"
    )


def write_compile_artifacts(
    *,
    profile_skip_write: bool,
    project_dir: Path,
    analysis: CompileAnalysis,
    manifest_payload: dict[str, object] | None,
    status: TransientStatusReporter | None,
    prepared_artifacts: PreparedCompileArtifacts | None = None,
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
        _ = start_compile_phase(status=status, message="Writing compiled artifacts...")
        staged: WrittenTarget | None = (
            prepared_artifacts.publish(target_dir=target_dir, manifest=manifest_payload)
            if prepared_artifacts is not None
            else None
        )
        written = (
            staged
            if staged is not None
            else write_static_compile_target(
                target_dir=target_dir,
                adapter=analysis.adapter,
                project=analysis.graph.project,
                manifest=manifest_payload,
            )
        )
    write_ms: int = elapsed_ms(write_start)
    if not profile_skip_write:
        _ = complete_compile_phase(
            status=status, message=f"Wrote compiled artifacts. ({write_ms / 1000:.2f}s)"
        )
    return CompileWriteResult(written=written, write_ms=write_ms)
