"""Scenario snapshot capture command runner."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.scenario.capture_run import run_scenario_capture_run
from sqlbuild.cli.commands.main.helpers.scenario.dialect import require_scenario_capture_dialect
from sqlbuild.cli.commands.main.helpers.scenario.selection import select_scenarios
from sqlbuild.cli.commands.main.helpers.scenario.snapshot_limits import (
    build_scenario_snapshot_capture_limits,
    scenario_snapshot_capture_warning,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection.core import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.main.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.progress.connection import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress.core import write_execution_header
from sqlbuild.cli.commands.main.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.compiler.compile.models.core import CompiledSqlScenario
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.scenario.models import ScenarioSnapshotCaptureLimits
from sqlbuild.shared.constants import SCENARIO_CLI_SQL_VALIDATION_REQUIRED
from sqlbuild.shared.helpers.output.colors import supports_color
from sqlbuild.spec.models.project import (
    resolve_effective_adapter_name,
    resolve_effective_scenario_config,
)


def run_scenario_capture(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    selectors: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    retain: bool = False,
    force: bool = False,
    max_snapshot_rows: int | None = None,
    max_snapshot_total_rows: int | None = None,
    max_snapshot_bytes: int | None = None,
    max_snapshot_total_bytes: int | None = None,
) -> int:
    """Execute the scenario capture command."""

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
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
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

    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
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
    return run_scenario_capture_run(
        project_dir=effective_project_dir,
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        connection_config=connection_config,
        adapter=adapter,
        adapter_name=adapter_name,
        project_name=discovered_inputs.project_config.name,
        capture_dialect=capture_dialect,
        capture_limits=capture_limits,
        retain=retain,
        progress_stream=progress_stream,
        use_color=use_color,
    )


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
        if "sql_analysis" in setting_overrides
        else discovered_inputs.project_config.settings.sql_analysis
    )
    sql_validation_enabled: bool = (
        discovered_inputs.local_config.settings.sql_validation
        if "sql_validation" in setting_overrides
        else discovered_inputs.project_config.settings.sql_validation
    )
    return sql_analysis_enabled and sql_validation_enabled
