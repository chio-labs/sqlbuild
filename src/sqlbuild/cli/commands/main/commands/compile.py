"""CLI compile command entry point."""

from __future__ import annotations

import time
from pathlib import Path

from sqlbuild.cli.commands.helpers.compile.models import CompileAnalysis, CompileWriteResult
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
from sqlbuild.shared.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.shared.helpers.output.colors import supports_color


def run_compile(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    selected_target: str | None = None,
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
            selected_target=selected_target,
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
    selected_target: str | None,
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

    analysis: CompileAnalysis = analyze_compile_project(
        project_dir=project_dir,
        no_sql_validation=no_sql_validation,
        selected_target=selected_target,
        lineage_mode=lineage_mode,
        cli_vars=cli_vars,
        profile_skip_discovery_sql_analysis=profile_skip_discovery_sql_analysis,
        profile_skip_column_inference=profile_skip_column_inference,
        profile_skip_contracts=profile_skip_contracts,
        status=status,
    )
    manifest_payload: dict[str, object] | None = build_compile_manifest_payload(
        manifest=manifest,
        analysis=analysis,
        status=status,
    )
    write_compile_dag_artifact(
        dag_path=dag_path,
        project_dir=project_dir,
        analysis=analysis,
        status=status,
    )
    write_result: CompileWriteResult = write_compile_artifacts(
        profile_skip_write=profile_skip_write,
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
