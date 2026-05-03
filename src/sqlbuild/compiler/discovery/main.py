"""Discovery entrypoints."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.helpers.project_config import (
    load_local_config,
    load_project_config,
)
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


def discover_project_inputs(*, project_dir: Path) -> tuple[ProjectConfig, LocalConfig]:
    """Load shared and local project configuration from disk."""

    return (
        load_project_config(project_dir=project_dir),
        load_local_config(project_dir=project_dir),
    )
