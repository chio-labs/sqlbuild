"""Discovery entrypoints."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.helpers.filesystem import (
    discover_adapter_file,
    discover_audit_files,
    discover_dbt_manifest_file,
    discover_macro_files,
    discover_model_files,
    discover_schema_files,
    discover_seed_files,
    discover_source_files,
    discover_test_files,
)
from sqlbuild.compiler.discovery.helpers.yml_project import (
    load_local_config,
    load_project_config,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


def discover_project_inputs(*, project_dir: Path) -> DiscoveredProjectInputs:
    """Load all raw project inputs from disk before semantic resolution."""

    project_config: ProjectConfig = load_project_config(project_dir=project_dir)
    local_config: LocalConfig = load_local_config(project_dir=project_dir)

    return DiscoveredProjectInputs(
        project_config=project_config,
        local_config=local_config,
        model_files=discover_model_files(project_dir=project_dir),
        schema_files=discover_schema_files(project_dir=project_dir),
        source_files=discover_source_files(project_dir=project_dir),
        seed_files=discover_seed_files(project_dir=project_dir),
        test_files=discover_test_files(project_dir=project_dir),
        audit_files=discover_audit_files(project_dir=project_dir),
        macro_files=discover_macro_files(project_dir=project_dir),
        dbt_manifest_file=discover_dbt_manifest_file(project_dir=project_dir),
        adapter_file=discover_adapter_file(project_dir=project_dir),
    )
