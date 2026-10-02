"""SQL-only discovery of the inputs that decide a model's description."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_model_files,
    discover_model_schema_files,
)
from sqlbuild.compiler.discovery._helpers.yml.project import load_project_config
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveryFileFault
from sqlbuild.spec.contracts.models import LocalConfig


def discover_model_description_inputs(*, project_dir: Path) -> DiscoveredProjectInputs:
    """Load project config, model files and model schemas without importing project Python."""

    return DiscoveredProjectInputs(
        project_config=load_project_config(project_dir=project_dir),
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
