"""Scenario snapshot capture command runner."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands._helpers.scenario_capture.capture_run import (
    build_scenario_capture_settings,
    run_scenario_capture_run,
)
from sqlbuild.cli.commands._helpers.scenario_capture.dialect import require_scenario_capture_dialect
from sqlbuild.cli.commands._helpers.scenario_capture.snapshot_limits import (
    build_scenario_snapshot_capture_limits,
    scenario_snapshot_capture_warning,
)
from sqlbuild.cli.commands._helpers.scenario_execution.selection import select_scenarios
from sqlbuild.cli.commands.constants import (
    SCENARIO_CLI_SQL_VALIDATION_REQUIRED,
    SQL_ANALYSIS_CONFIG_KEY,
    SQL_VALIDATION_CONFIG_KEY,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    ScenarioCaptureCommandRequest,
    ScenarioRunOutputContext,
    ScenarioSnapshotLimitInputs,
)
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.cli.progress.main._write_execution_header import write_execution_header
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
)
from sqlbuild.executor.scenario.models import ScenarioSnapshotCaptureLimits
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.main.resolve_effective_scenario_config import (
    resolve_effective_scenario_config,
)


def run_scenario_capture(request: ScenarioCaptureCommandRequest) -> int:
    """Execute the scenario capture command."""

    project_dir: Path | None = request.project_dir
    no_sql_validation: bool = request.no_sql_validation
    no_color: bool = request.no_color
    selectors: tuple[str, ...] = request.selectors
    exclude: tuple[str, ...] = request.exclude
    retain: bool = request.retain
    limit_inputs: ScenarioSnapshotLimitInputs = request.limit_inputs
    force: bool = limit_inputs.force
    if no_sql_validation:
        raise CliUserError(
            "scenario capture requires SQL analysis and SQL validation",
            code=SCENARIO_CLI_SQL_VALIDATION_REQUIRED,
            help=(
                "Enable settings.sql_analysis and settings.sql_validation when capturing snapshots "
                "for local scenario replay."
            ),
        )

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    _validate_capture_sql_analysis_enabled(discovered_inputs=discovered_inputs)
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=adapter_name, project_dir=effective_project_dir
    )
    capture_dialect: str = require_scenario_capture_dialect(
        adapter=adapter, adapter_name=adapter_name
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stdout
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
        command="sqb scenario capture",
        target=target_label,
        concurrency=1,
        use_color=use_color,
    )
    progress_stream.write(f"{scenario_snapshot_capture_warning(force=force)}\n\n")
    progress_stream.flush()

    with OperationLifecycle(operation_kind="project", operation_name="project_compile"):
        pipeline_result: CompilePipelineResult = run_compile_pipeline(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            options=CompilePipelineOptions(
                no_sql_validation=no_sql_validation,
                connection_config=connection_config,
                external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                    project_dir=effective_project_dir,
                    discovered_inputs=discovered_inputs,
                ),
            ),
            hooks=ConnectionHooks(
                on_progress=planning_progress.on_progress,
                on_connection_start=connection_progress.on_connection_start,
                on_connection_complete=lambda connection_count, elapsed_seconds: (
                    connection_progress.on_connection_complete(
                        connection_count=connection_count, elapsed_seconds=elapsed_seconds
                    )
                ),
                on_connection_error=lambda connection_count, elapsed_seconds: (
                    connection_progress.on_connection_error(
                        connection_count=connection_count, elapsed_seconds=elapsed_seconds
                    )
                ),
            ),
        )
    scenarios: tuple[CompiledSqlScenario, ...] = select_scenarios(
        project=pipeline_result.project,
        selectors=selectors,
        exclude=exclude,
        project_dir=effective_project_dir,
    )
    capture_limits: ScenarioSnapshotCaptureLimits = build_scenario_snapshot_capture_limits(
        scenario_config=resolve_effective_scenario_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        limit_inputs=limit_inputs,
    )
    exit_code, _ = run_scenario_capture_run(
        project_dir=effective_project_dir,
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        connection_config=connection_config,
        adapter=adapter,
        adapter_name=adapter_name,
        project_name=discovered_inputs.project_config.name,
        settings=build_scenario_capture_settings(
            capture_adapter=adapter_name,
            capture_dialect=capture_dialect,
            retain=retain,
            limits=capture_limits,
        ),
        output_context=ScenarioRunOutputContext(
            progress_stream=progress_stream,
            use_color=use_color,
        ),
    )
    return exit_code


def _validate_capture_sql_analysis_enabled(*, discovered_inputs: DiscoveredProjectInputs) -> None:
    if not _effective_sql_analysis_and_validation_enabled(discovered_inputs=discovered_inputs):
        raise CliUserError(
            "scenario capture requires SQL analysis and SQL validation",
            code=SCENARIO_CLI_SQL_VALIDATION_REQUIRED,
            help=(
                "Enable settings.sql_analysis and settings.sql_validation when capturing snapshots "
                "for local scenario replay."
            ),
        )


def _effective_sql_analysis_and_validation_enabled(
    *, discovered_inputs: DiscoveredProjectInputs
) -> bool:
    setting_overrides: frozenset[str] = discovered_inputs.local_config.setting_overrides
    sql_analysis_enabled: bool = (
        discovered_inputs.local_config.settings.sql_analysis
        if SQL_ANALYSIS_CONFIG_KEY in setting_overrides
        else discovered_inputs.project_config.settings.sql_analysis
    )
    sql_validation_enabled: bool = (
        discovered_inputs.local_config.settings.sql_validation
        if SQL_VALIDATION_CONFIG_KEY in setting_overrides
        else discovered_inputs.project_config.settings.sql_validation
    )
    return sql_analysis_enabled and sql_validation_enabled
