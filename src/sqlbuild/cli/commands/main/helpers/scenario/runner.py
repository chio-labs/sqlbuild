"""Scenario command runner."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.cli.commands.main.helpers.scenario.constants import SUCCESS_STATUS
from sqlbuild.cli.commands.main.helpers.scenario.dialect import require_scenario_capture_dialect
from sqlbuild.cli.commands.main.helpers.scenario.local_run import run_local_scenarios
from sqlbuild.cli.commands.main.helpers.scenario.result_output import render_result_error
from sqlbuild.cli.commands.main.helpers.scenario.selection import select_scenarios
from sqlbuild.cli.commands.main.helpers.scenario.snapshot_limits import (
    build_scenario_snapshot_capture_limits,
    scenario_snapshot_capture_warning,
)
from sqlbuild.cli.commands.main.helpers.scenario.warehouse_run import run_warehouse_scenarios
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.execution_json import (
    format_scenario_snapshot_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.main.shared.helpers.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress import write_execution_header
from sqlbuild.compiler.compile.models.core import CompiledSqlScenario
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.pipeline.main.run import (
    run_scenario_capture_pipeline,
    select_scenario_snapshot_capture_candidates,
)
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureRunResult,
)
from sqlbuild.shared.constants import (
    SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED,
    SCENARIO_CLI_LOCAL_SNAPSHOT_FLAG_REQUIRED,
    SCENARIO_CLI_SQL_VALIDATION_REQUIRED,
)
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.shared.helpers.status import TransientStatusReporter
from sqlbuild.spec.models.project import (
    resolve_effective_adapter_name,
    resolve_effective_scenario_config,
)

_SCENARIO_NAME_WIDTH: int = 64
_EXPECTATION_LABEL_WIDTH: int = 10
_EXPECTATION_NAME_WIDTH: int = 50
_CAPTURE_RELATION_KIND_WIDTH: int = 8
_CAPTURE_RELATION_NAME_WIDTH: int = _SCENARIO_NAME_WIDTH - 4 - _CAPTURE_RELATION_KIND_WIDTH - 1


def run_scenario(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    selectors: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    retain: bool = False,
    local: bool = False,
    strict: bool = False,
    sync_snapshots: bool = False,
    refresh: bool = False,
    force: bool = False,
    max_snapshot_rows: int | None = None,
    max_snapshot_total_rows: int | None = None,
    max_snapshot_bytes: int | None = None,
    max_snapshot_total_bytes: int | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the scenario test command."""

    if local and retain:
        raise CliUserError(
            "scenario test --local does not support --retain",
            code=SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED,
            help=("Local scenario DuckDB files are always kept under target/run/scenarios/."),
        )
    if not local and (sync_snapshots or refresh):
        raise CliUserError(
            "scenario snapshot sync flags require --local",
            code=SCENARIO_CLI_LOCAL_SNAPSHOT_FLAG_REQUIRED,
            help=(
                "Use sqb scenario test --local --sync-snapshots or "
                "sqb scenario test --local --refresh."
            ),
        )
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    if local:
        _validate_local_scenario_sql_analysis_enabled(
            discovered_inputs=discovered_inputs,
            no_sql_validation=no_sql_validation,
        )
    project_adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter_name: str = BuiltinAdapter.DUCKDB.value if local else project_adapter_name
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
    project_adapter: BaseAdapter = resolve_adapter(
        project_adapter_name,
        project_dir=effective_project_dir,
    )
    local_capture_dialect: str = ""
    if local:
        local_capture_dialect = require_scenario_capture_dialect(
            adapter=project_adapter, adapter_name=project_adapter_name
        )
    connection_config: dict[str, object] = (
        {"database": ":memory:"}
        if local
        else resolve_project_connection_config(
            discovered_inputs=discovered_inputs,
            project_dir=effective_project_dir,
        )
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    target_label: str | None = " ".join(selectors) if selectors else None
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write("\n")
    write_execution_header(
        stream=progress_stream,
        command="sqb scenario test --local" if local else "sqb scenario test",
        target=target_label,
        concurrency=1,
        use_color=use_color,
    )

    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=True if local else no_sql_validation,
        source_deferral_enabled=False,
        connection_config=connection_config,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
        ),
    )
    scenarios: tuple[CompiledSqlScenario, ...] = select_scenarios(
        project=pipeline_result.project,
        selectors=selectors,
        exclude=exclude,
        project_dir=effective_project_dir,
    )
    if local and (sync_snapshots or refresh):
        capture_results: list[ScenarioSnapshotCaptureRunResult] = []
        capture_exit_code: int = _sync_local_snapshots(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            local_pipeline_result=pipeline_result,
            local_scenarios=scenarios,
            local_adapter=adapter,
            project_adapter=project_adapter,
            project_adapter_name=project_adapter_name,
            capture_dialect=local_capture_dialect,
            project_connection_config=resolve_project_connection_config(
                discovered_inputs=discovered_inputs,
                project_dir=effective_project_dir,
            ),
            project_name=discovered_inputs.project_config.name,
            no_sql_validation=no_sql_validation,
            refresh=refresh,
            force=force,
            max_snapshot_rows=max_snapshot_rows,
            max_snapshot_total_rows=max_snapshot_total_rows,
            max_snapshot_bytes=max_snapshot_bytes,
            max_snapshot_total_bytes=max_snapshot_total_bytes,
            progress_stream=progress_stream,
            use_color=use_color,
            capture_results_out=capture_results,
        )
        if capture_exit_code != 0:
            write_execution_json_output(
                payload=format_scenario_snapshot_execution_json(
                    results=tuple(capture_results),
                    refresh=refresh,
                ),
                json_output=json_output,
                json_output_path=json_output_path,
            )
            return capture_exit_code
    if not local:
        return run_warehouse_scenarios(
            pipeline_result=pipeline_result,
            scenarios=scenarios,
            connection_config=connection_config,
            adapter=adapter,
            adapter_name=adapter_name,
            project_name=discovered_inputs.project_config.name,
            target_dir=effective_project_dir / "target",
            retain=retain,
            progress_stream=progress_stream,
            use_color=use_color,
            json_output=json_output,
            json_output_path=json_output_path,
        )
    return run_local_scenarios(
        project_dir=effective_project_dir,
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        adapter=adapter,
        project_name=discovered_inputs.project_config.name,
        strict=strict,
        capture_adapter=project_adapter_name,
        capture_dialect=local_capture_dialect,
        target_dir=effective_project_dir / "target",
        progress_stream=progress_stream,
        use_color=use_color,
        json_output=json_output,
        json_output_path=json_output_path,
    )


def _validate_local_scenario_sql_analysis_enabled(
    *, discovered_inputs: DiscoveredProjectInputs, no_sql_validation: bool
) -> None:
    if no_sql_validation or not _effective_sql_analysis_and_validation_enabled(
        discovered_inputs=discovered_inputs
    ):
        raise CliUserError(
            "scenario test --local requires SQL analysis and SQL validation",
            code=SCENARIO_CLI_SQL_VALIDATION_REQUIRED,
            help=(
                "Enable settings.sql_analysis and settings.sql_validation when running local "
                "scenario replay, snapshot sync, or snapshot refresh."
            ),
        )


def _effective_sql_analysis_and_validation_enabled(
    *, discovered_inputs: DiscoveredProjectInputs
) -> bool:
    setting_overrides: frozenset[str] = discovered_inputs.local_config.setting_overrides
    sql_analysis_enabled: bool = (
        discovered_inputs.local_config.settings.sql_analysis
        if "sql_analysis" in setting_overrides
        else discovered_inputs.project_config.settings.sql_analysis
    )
    sql_validation_enabled: bool = (
        discovered_inputs.local_config.settings.sql_validation
        if "sql_validation" in setting_overrides
        else discovered_inputs.project_config.settings.sql_validation
    )
    return sql_analysis_enabled and sql_validation_enabled


def _sync_local_snapshots(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    local_pipeline_result: CompilePipelineResult,
    local_scenarios: tuple[CompiledSqlScenario, ...],
    local_adapter: BaseAdapter,
    project_adapter: BaseAdapter,
    project_adapter_name: str,
    capture_dialect: str,
    project_connection_config: dict[str, object],
    project_name: str,
    no_sql_validation: bool,
    refresh: bool,
    force: bool,
    max_snapshot_rows: int | None,
    max_snapshot_total_rows: int | None,
    max_snapshot_bytes: int | None,
    max_snapshot_total_bytes: int | None,
    progress_stream: TextIO,
    use_color: bool,
    capture_results_out: list[ScenarioSnapshotCaptureRunResult] | None = None,
) -> int:
    capture_names: tuple[str, ...] = select_scenario_snapshot_capture_candidates(
        project_dir=project_dir,
        pipeline_result=local_pipeline_result,
        scenarios=local_scenarios,
        adapter=local_adapter,
        project_name=project_name,
        capture_adapter=project_adapter_name,
        capture_dialect=capture_dialect,
        refresh=refresh,
    )
    if not capture_names:
        progress_stream.write("\nSnapshots are fresh.\n")
        progress_stream.flush()
        return 0

    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=project_adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    project_pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=project_adapter,
        no_sql_validation=no_sql_validation,
        source_deferral_enabled=False,
        connection_config=project_connection_config,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
        ),
    )
    capture_scenarios: tuple[CompiledSqlScenario, ...] = select_scenarios(
        project=project_pipeline_result.project,
        selectors=capture_names,
        project_dir=project_dir,
    )
    phase_name: str = "Refresh" if refresh else "Sync"
    header: str = f"Snapshot {phase_name} ({len(capture_scenarios)} selected)"
    style: CliStyle = CliStyle(use_color=use_color)
    styled_header: str = style.success_strong(header)
    progress_stream.write(f"\n{styled_header}\n\n")
    progress_stream.write(f"{scenario_snapshot_capture_warning(force=force)}\n\n")
    progress_stream.flush()
    scenario_status: TransientStatusReporter = TransientStatusReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=project_adapter_name,
        blank_line_after_complete=True,
        stream=progress_stream,
        use_color=use_color,
    )
    status_is_tty: bool = hasattr(progress_stream, "isatty") and progress_stream.isatty()
    if not status_is_tty:
        progress_stream.write("Capturing snapshots...\n\n")
        progress_stream.flush()
    capture_limits: ScenarioSnapshotCaptureLimits = build_scenario_snapshot_capture_limits(
        scenario_config=resolve_effective_scenario_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        max_rows_per_relation=max_snapshot_rows,
        max_total_rows=max_snapshot_total_rows,
        max_bytes_per_relation=max_snapshot_bytes,
        max_total_bytes=max_snapshot_total_bytes,
        force=force,
    )
    results: tuple[ScenarioSnapshotCaptureRunResult, ...] = run_scenario_capture_pipeline(
        project_dir=project_dir,
        pipeline_result=project_pipeline_result,
        scenarios=capture_scenarios,
        connection_config=project_connection_config,
        adapter=project_adapter,
        project_name=project_name,
        captured_at=_captured_at(),
        capture_adapter=project_adapter_name,
        capture_dialect=capture_dialect,
        sqlbuild_version=_sqlbuild_version(),
        retain=False,
        capture_limits=capture_limits,
        on_connection_start=execution_connection_progress.on_connection_start,
        on_connection_complete=execution_connection_progress.on_connection_complete,
        on_connection_error=execution_connection_progress.on_connection_error,
        on_scenario_start=lambda _scenario: (
            scenario_status.start("Capturing snapshots...") if status_is_tty else None
        ),
        on_scenario_complete=lambda _scenario, _scenario_plan, result: _complete_snapshot_sync(
            scenario_status=scenario_status,
            status_is_tty=status_is_tty,
            project_dir=project_dir,
            refresh=refresh,
            result=result,
            progress_stream=progress_stream,
            use_color=use_color,
        ),
    )
    if capture_results_out is not None:
        capture_results_out.extend(results)
    scenario_status.close()
    pass_count: int = sum(1 for result in results if result.status == SUCCESS_STATUS)
    fail_count: int = len(results) - pass_count
    summary_prefix: str = "REFRESH" if refresh else "SYNC"
    progress_stream.write(
        f"\n{summary_prefix}_PASS={pass_count}  {summary_prefix}_FAIL={fail_count}\n"
    )
    progress_stream.flush()
    return 0 if fail_count == 0 else 1


def _complete_snapshot_sync(
    *,
    scenario_status: TransientStatusReporter,
    status_is_tty: bool,
    project_dir: Path,
    refresh: bool,
    result: ScenarioSnapshotCaptureRunResult,
    progress_stream: TextIO,
    use_color: bool,
) -> None:
    if status_is_tty:
        scenario_status.close()
    success_status_text: str = "REFRESHED" if refresh else "CAPTURED"
    status_text: str = success_status_text if result.status == SUCCESS_STATUS else "FAIL"
    style: CliStyle = CliStyle(use_color=use_color)
    status: str = style.status(status_text)
    detail: str = _snapshot_capture_detail(result)
    progress_stream.write(f"{result.scenario_name:<{_SCENARIO_NAME_WIDTH}} {status}{detail}\n")
    if result.error_message:
        rendered_error_message: str = render_result_error(
            error_code=result.error_code,
            error_message=result.error_message,
            error_help=result.error_help,
            use_color=use_color,
        )
        error_line: str
        for error_line in rendered_error_message.splitlines():
            progress_stream.write(f"    {error_line}\n")
    _write_snapshot_capture_relation_rows(
        result=result, stream=progress_stream, use_color=use_color
    )
    if result.capture_result is not None and result.capture_result.manifest_path is not None:
        snapshot_path: str = _display_snapshot_path(
            manifest_path=result.capture_result.manifest_path,
            project_dir=project_dir,
        )
        progress_stream.write(f"    {'snapshot':<{_CAPTURE_RELATION_KIND_WIDTH}} {snapshot_path}\n")
    progress_stream.flush()


def _write_snapshot_capture_relation_rows(
    *, result: ScenarioSnapshotCaptureRunResult, stream: TextIO, use_color: bool
) -> None:
    if result.capture_result is None:
        return
    relation_result: ScenarioSnapshotCaptureRelationResult
    for relation_result in result.capture_result.relation_results:
        status_text: str = "PASS" if relation_result.status == SUCCESS_STATUS else "FAIL"
        style: CliStyle = CliStyle(use_color=use_color)
        status: str = style.status(status_text)
        row_label: str = "row" if relation_result.row_count == 1 else "rows"
        detail: str = (
            f"  {relation_result.row_count} {row_label}, "
            f"{_format_snapshot_size(relation_result.byte_count)}"
        )
        stream.write(
            f"    {relation_result.kind.value:<{_CAPTURE_RELATION_KIND_WIDTH}} "
            f"{relation_result.logical_name:<{_CAPTURE_RELATION_NAME_WIDTH}} "
            f"{status}{detail}\n"
        )


def _snapshot_capture_detail(result: ScenarioSnapshotCaptureRunResult) -> str:
    if result.capture_result is None:
        return ""
    relation_results: tuple[ScenarioSnapshotCaptureRelationResult, ...] = (
        result.capture_result.relation_results
    )
    relation_count: int = sum(
        1 for relation in relation_results if relation.status == SUCCESS_STATUS
    )
    row_count: int = sum(relation.row_count for relation in relation_results)
    relation_label: str = "relation" if relation_count == 1 else "relations"
    row_label: str = "row" if row_count == 1 else "rows"
    return f"  {relation_count} {relation_label}, {row_count} {row_label}"


def _format_snapshot_size(byte_count: int) -> str:
    if byte_count < 1024:
        return f"{byte_count} B"
    kibibytes: float = byte_count / 1024
    if kibibytes < 1024:
        return f"{kibibytes:.1f} KB"
    mebibytes: float = kibibytes / 1024
    return f"{mebibytes:.1f} MB"


def _display_snapshot_path(*, manifest_path: Path, project_dir: Path) -> str:
    try:
        return manifest_path.relative_to(project_dir).as_posix()
    except ValueError:
        return manifest_path.as_posix()


def _captured_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "unknown"
