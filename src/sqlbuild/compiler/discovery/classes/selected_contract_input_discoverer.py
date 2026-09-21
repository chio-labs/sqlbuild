"""Bounded discovery for selected contract consumers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_model_files,
    discover_model_schema_files,
    discover_schema_files,
    discover_source_files,
    discover_test_files,
)
from sqlbuild.compiler.discovery._helpers.yml.project import (
    load_local_config,
    load_project_config,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


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

        return DiscoveredProjectInputs(
            project_config=load_project_config(project_dir=project_dir),
            local_config=load_local_config(project_dir=project_dir),
            project_dir=project_dir,
            model_files=discover_model_files(
                project_dir=project_dir,
                extract_implicit_alias_columns=False,
                extract_output_column_locations=False,
                selected_model_names=referenced_model_names,
            ),
            model_schema_files=discover_model_schema_files(project_dir=project_dir),
            schema_files=discover_schema_files(project_dir=project_dir),
            source_files=discover_source_files(project_dir=project_dir),
            test_files=discover_test_files(
                project_dir=project_dir,
                selected_paths=selected_test_paths,
            ),
        )
