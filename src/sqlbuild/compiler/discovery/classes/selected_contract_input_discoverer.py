"""Bounded discovery for selected contract consumers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.core import discover_model_schema_files
from sqlbuild.compiler.discovery._helpers.native.declarations import (
    prepare_native_declaration_layout,
)
from sqlbuild.compiler.discovery._helpers.native.model_files import discover_native_model_files
from sqlbuild.compiler.discovery._helpers.native.sql_test_files import discover_native_test_files
from sqlbuild.compiler.discovery._helpers.native.yaml_files import (
    discover_native_schema_files,
    discover_native_source_files,
)
from sqlbuild.compiler.discovery._helpers.yml.project import (
    load_local_config,
    load_project_config,
)
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


class SelectedContractInputDiscoverer:
    """Discover contracts and selected SQL tests without unrelated runtime resources."""

    @staticmethod
    def discover(
        *,
        project_dir: Path,
        selected_test_paths: frozenset[Path],
        referenced_model_names: frozenset[str],
    ) -> DiscoveredProjectInputs:
        """Build selected contract inputs without importing Python runtime resources."""

        project_config: ProjectConfig = load_project_config(project_dir=project_dir)
        local_config: LocalConfig = load_local_config(project_dir=project_dir)
        with DirectorySnapshot.scope(project_dir=project_dir):
            prepare_native_declaration_layout(project_dir=project_dir)
            return DiscoveredProjectInputs(
                project_config=project_config,
                local_config=local_config,
                project_dir=project_dir,
                model_files=discover_native_model_files(
                    project_dir=project_dir,
                    extract_implicit_alias_columns=False,
                    extract_output_column_locations=False,
                    selected_model_names=referenced_model_names,
                ),
                model_schema_files=discover_model_schema_files(project_dir=project_dir),
                schema_files=discover_native_schema_files(project_dir=project_dir),
                source_files=discover_native_source_files(project_dir=project_dir),
                test_files=discover_native_test_files(
                    project_dir=project_dir,
                    selected_paths=selected_test_paths,
                ),
            )
