"""Lightweight project configuration discovery entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.yml.project import load_local_config, load_project_config
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def discover_project_configuration(*, project_dir: Path) -> DiscoveredProjectInputs:
    """Load project and local configuration without importing project extensions."""

    with OperationLifecycle(operation_kind="project", operation_name="project_discovery"):
        return DiscoveredProjectInputs(
            project_dir=project_dir,
            project_config=load_project_config(project_dir=project_dir),
            local_config=load_local_config(project_dir=project_dir),
        )
