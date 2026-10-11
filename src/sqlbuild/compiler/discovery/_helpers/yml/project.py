"""Project config loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.yml.target_warehouses import (
    reject_unsupported_target_warehouses,
)
from sqlbuild.compiler.discovery.constants import SQL_ANALYSIS_CONFIG_KEY
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def load_project_config(*, project_dir: Path) -> ProjectConfig:
    """Load project config from the given project directory."""

    return cast(ProjectConfig, _native.load_project_config_file(project_dir))


def load_local_config(*, project_dir: Path) -> LocalConfig:
    """Load local config if present."""

    return cast(LocalConfig, _native.load_local_config_file(project_dir))


def validate_local_sql_analysis_policy(
    *, project_dir: Path, project_config: ProjectConfig, local_config: LocalConfig
) -> None:
    """Reject a local project-wide SQL analysis opt-out when the project requires analysis."""

    _native.validate_local_sql_analysis(
        project_dir,
        (
            project_config.settings.require_sql_analysis,
            SQL_ANALYSIS_CONFIG_KEY in local_config.setting_overrides,
            local_config.settings.sql_analysis,
        ),
    )


def validate_target_warehouses_adapter(
    *, project_dir: Path, project_config: ProjectConfig, local_config: LocalConfig
) -> None:
    """Reject command-group warehouses for adapters without a session warehouse."""

    reject_unsupported_target_warehouses(
        project_dir=project_dir,
        project_config=project_config,
        local_config=local_config,
        project_config_path=_native.resolve_config_file_path(project_dir, False),
        local_config_path=_native.resolve_config_file_path(project_dir, True),
    )
