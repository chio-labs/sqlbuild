"""SQL-only discovery of the inputs that decide a model's description."""

from __future__ import annotations

from pathlib import Path

from sqlbuild._native import (
    directory_snapshot_scope,
    discover_model_files,
    discover_model_schema_files,
    load_project_config_file,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveryFileFault
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def discover_model_description_inputs(*, project_dir: Path) -> DiscoveredProjectInputs:
    """Load project config, model files and model schemas without importing project Python."""

    project_config: ProjectConfig = load_project_config_file(project_dir)
    with directory_snapshot_scope(project_dir=project_dir):
        return DiscoveredProjectInputs(
            project_config=project_config,
            local_config=LocalConfig(),
            model_files=discover_model_files(
                project_dir=project_dir,
                extract_implicit_alias_columns=False,
                extract_output_column_locations=False,
                on_fault=_skip_unreadable_file,
            ),
            model_schema_files=discover_model_schema_files(
                project_dir=project_dir, on_fault=_skip_unreadable_file
            ),
        )


def _skip_unreadable_file(fault: DiscoveryFileFault) -> None:
    """Leave an unparseable file unresolved; format reports that file's own faults."""

    del fault
