"""CLI compile command entry point."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from sqlbuild.cli.commands.helpers.compile.models import (
    CompileAnalysis,
    CompileCommandRequest,
    CompileWriteResult,
)
from sqlbuild.cli.commands.helpers.compile.output import (
    format_compile_json,
    format_compile_text,
)
from sqlbuild.cli.commands.helpers.compile.pipeline import (
    analyze_compile_project,
    build_compile_manifest_payload,
    write_compile_artifacts,
    write_compile_dag_artifact,
)
from sqlbuild.cli.commands.helpers.compile.status import elapsed_ms, start_compile_status
from sqlbuild.cli.commands.helpers.compile.types import CompileLineageMode
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.supports_color import supports_color


def run_compile(request: CompileCommandRequest) -> int:
    """Execute the compile command."""

    total_start: float = time.monotonic()
    effective_request: CompileCommandRequest = (
        request if request.project_dir is not None else replace(request, project_dir=Path.cwd())
    )
    status: TransientStatusReporter | None = start_compile_status(
        json_output=request.json_output,
        no_color=request.no_color,
    )
    try:
        return _run_compile_with_status(
            request=effective_request,
            total_start=total_start,
            status=status,
        )
    finally:
        if status is not None:
            status.close()


def _run_compile_with_status(
    *,
    request: CompileCommandRequest,
    total_start: float,
    status: TransientStatusReporter | None,
) -> int:
    """Execute compile after the optional interactive status reporter is initialized."""

    project_dir: Path = request.project_dir if request.project_dir is not None else Path.cwd()
    json_output: bool = request.json_output
    manifest: bool = request.manifest
    no_color: bool = request.no_color
    lineage_mode: CompileLineageMode = request.lineage_mode
    analysis: CompileAnalysis = analyze_compile_project(
        project_dir=project_dir,
        no_sql_validation=request.no_sql_validation,
        selected_target=request.selected_target,
        lineage_mode=lineage_mode,
        cli_vars=request.cli_vars,
        profile_flags=request.profile_flags,
        status=status,
    )
    manifest_payload: dict[str, object] | None = build_compile_manifest_payload(
        manifest=manifest,
        analysis=analysis,
        status=status,
    )
    write_compile_dag_artifact(
        dag_path=request.dag_path,
        project_dir=project_dir,
        analysis=analysis,
        status=status,
    )
    write_result: CompileWriteResult = write_compile_artifacts(
        profile_skip_write=request.profile_flags.skip_write,
        project_dir=project_dir,
        analysis=analysis,
        manifest_payload=manifest_payload,
        status=status,
    )
    timings_ms: dict[str, int] = {
        "discover_ms": analysis.discover_ms,
        "graph_ms": analysis.graph_ms,
        "lineage_ms": analysis.lineage_ms,
        "contracts_ms": analysis.contract_ms,
        "write_ms": write_result.write_ms,
        "total_ms": elapsed_ms(total_start),
    }
    exit_code: int = 1 if any(diagnostic.is_error for diagnostic in analysis.diagnostics) else 0

    if status is not None:
        status.close()

    if json_output:
        print(
            format_compile_json(
                graph=analysis.graph,
                written=write_result.written,
                manifest=manifest,
                timings_ms=timings_ms,
                lineage=analysis.lineage,
                lineage_mode=lineage_mode,
                diagnostics=analysis.diagnostics,
            )
        )
        return exit_code

    print(
        format_compile_text(
            graph=analysis.graph,
            written=write_result.written,
            manifest=manifest,
            lineage=analysis.lineage,
            lineage_mode=lineage_mode,
            diagnostics=analysis.diagnostics,
            use_color=(not no_color) and supports_color(),
        )
    )
    return exit_code
