"""Discovery entrypoints."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.constants import SQL_ANALYSIS_SETTING_KEY
from sqlbuild.compiler.discovery.helpers.filesystem.aggregation import (
    build_discovered_project_inputs,
)
from sqlbuild.compiler.discovery.helpers.validation.discovery import validate_discovered_inputs
from sqlbuild.compiler.discovery.helpers.yml.project import (
    load_local_config,
    load_project_config,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def discover_project_inputs(
    *, project_dir: Path, sql_analysis_enabled_override: bool | None = None
) -> DiscoveredProjectInputs:
    """Load all raw project inputs from disk before semantic resolution."""

    project_config: ProjectConfig = load_project_config(project_dir=project_dir)
    local_config: LocalConfig = load_local_config(project_dir=project_dir)
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
    )
    validate_discovered_inputs(discovered_inputs)
    return discovered_inputs
