"""Discovery entrypoints."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.aggregation import (
    build_discovered_project_inputs,
)
from sqlbuild.compiler.discovery._helpers.filesystem.python_paths import (
    validate_project_python_paths,
)
from sqlbuild.compiler.discovery._helpers.validation.discovery import validate_discovered_inputs
from sqlbuild.compiler.discovery._helpers.yml.project import (
    load_local_config,
    load_project_config,
)
from sqlbuild.compiler.discovery.constants import SQL_ANALYSIS_SETTING_KEY
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def discover_project_inputs(
    *,
    project_dir: Path,
    sql_analysis_enabled_override: bool | None = None,
    extract_output_column_locations: bool = True,
) -> DiscoveredProjectInputs:
    """Load all raw project inputs from disk before semantic resolution."""

    with OperationLifecycle(operation_kind="project", operation_name="project_discovery"):
        return _discover_project_inputs(
            project_dir=project_dir,
            sql_analysis_enabled_override=sql_analysis_enabled_override,
            extract_output_column_locations=extract_output_column_locations,
        )


def _discover_project_inputs(
    *,
    project_dir: Path,
    sql_analysis_enabled_override: bool | None,
    extract_output_column_locations: bool,
) -> DiscoveredProjectInputs:
    with OperationLifecycle(operation_kind="project", operation_name="discovery_project_assembly"):
        return _assemble_discovered_project_inputs(
            project_dir=project_dir,
            sql_analysis_enabled_override=sql_analysis_enabled_override,
            extract_output_column_locations=extract_output_column_locations,
        )


def _assemble_discovered_project_inputs(
    *,
    project_dir: Path,
    sql_analysis_enabled_override: bool | None,
    extract_output_column_locations: bool,
) -> DiscoveredProjectInputs:
    project_config: ProjectConfig = load_project_config(project_dir=project_dir)
    local_config: LocalConfig = load_local_config(project_dir=project_dir)
    validate_project_python_paths(project_dir=project_dir)
    sql_analysis_enabled: bool = (
        sql_analysis_enabled_override
        if sql_analysis_enabled_override is not None
        else (
            local_config.settings.sql_analysis
            if SQL_ANALYSIS_SETTING_KEY in local_config.setting_overrides
            else project_config.settings.sql_analysis
        )
    )
    discovered_inputs: DiscoveredProjectInputs = build_discovered_project_inputs(
        project_dir=project_dir,
        project_config=project_config,
        local_config=local_config,
        sql_analysis_enabled=sql_analysis_enabled,
        extract_output_column_locations=extract_output_column_locations,
    )
    validate_discovered_inputs(discovered_inputs)
    from sqlbuild.runtime.event_exporting.main.configure_discovered_event_exporters import (
        configure_discovered_event_exporters,
    )

    _ = configure_discovered_event_exporters(discovered_inputs)
    return discovered_inputs
