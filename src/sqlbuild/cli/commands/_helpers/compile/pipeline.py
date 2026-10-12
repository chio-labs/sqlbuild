"""Compile pipeline phases: analysis, manifest, DAG, and artifact writing."""

from __future__ import annotations

import time
from pathlib import Path

from sqlbuild.cli.commands._helpers.compile.status import (
    complete_compile_phase,
    elapsed_ms,
    start_compile_phase,
)
from sqlbuild.cli.commands._helpers.compile.target_writer import (
    static_sql_test_planning_diagnostics,
    write_static_compile_target,
)
from sqlbuild.cli.commands.classes.native_artifact_batch import NativeArtifactBatch
from sqlbuild.cli.commands.classes.prepared_compile_artifacts import PreparedCompileArtifacts
from sqlbuild.cli.compile.models import (
    CompileAnalysis,
    CompileWriteResult,
)
from sqlbuild.cli.output.models import (
    WrittenTarget,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError, SqlTestReferenceError
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
)
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
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
    from sqlbuild.compiler.manifest.main.build_graph_manifest import build_graph_manifest

    manifest_start: float = time.monotonic()
    _ = start_compile_phase(status=status, message="Building manifest...")
    manifest_payload: dict[str, object] = build_graph_manifest(
        project=analysis.graph.project,
        plan_output=None,
        project_name=analysis.discovered_inputs.project_config.name,
        adapter_type=resolve_effective_adapter_name(
            project_config=analysis.discovered_inputs.project_config,
            local_config=analysis.discovered_inputs.local_config,
        ),
        graph=analysis.graph.native,
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
    dag_json: str = build_dag_json(
        graph=analysis.graph,
        project_name=analysis.discovered_inputs.project_config.name,
        python_graph=python_graph,
    )
    dag_batch: NativeArtifactBatch = NativeArtifactBatch(check_existing=False)
    dag_batch.queue(path=resolved_dag_path, contents=dag_json.encode("utf-8"))
    dag_batch.flush()
    _ = complete_compile_phase(
        status=status, message=f"Wrote DAG artifact. ({time.monotonic() - dag_start:.2f}s)"
    )


def compile_sql_test_planning_diagnostics(
    *,
    project_dir: Path,
    analysis: CompileAnalysis,
    prepared_artifacts: PreparedCompileArtifacts | None,
) -> tuple[CompilerDiagnostic, ...]:
    """Report SQL test planning errors when artifacts are withheld, reusing staged planning."""

    try:
        staged: tuple[CompilerDiagnostic, ...] | None = (
            prepared_artifacts.planning_diagnostics() if prepared_artifacts is not None else None
        )
        if staged is not None:
            return staged
        return static_sql_test_planning_diagnostics(
            target_dir=project_dir / "target",
            adapter=analysis.adapter,
            project=analysis.graph.project,
        )
    except (CompileInputError, PlannerInputError) as error:
        return (
            CompilerDiagnostic(
                phase=DiagnosticPhase.TEST,
                severity=DiagnosticSeverity.ERROR,
                code=error.code,
                message=str(error),
                help=error.help,
                location=error.location if isinstance(error, SqlTestReferenceError) else None,
            ),
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
