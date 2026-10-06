"""Offline validation of each target's connection selection."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.constants import PROJECT_CONFIG_FILENAME
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def validate_target_connections(
    *, project_dir: Path, project_config: ProjectConfig, local_config: LocalConfig
) -> None:
    """Reject targets whose connection cannot be chosen among several named connections."""

    target_name: str
    for target_name in sorted({*project_config.targets, *local_config.targets}):
        try:
            _ = resolve_target_config(
                project_config=project_config,
                local_config=local_config,
                target_name=target_name,
            )
        except SpecConfigError as error:
            raise ProjectConfigError(f"{project_dir / PROJECT_CONFIG_FILENAME} {error}") from error
