"""Sources attached natively by the compile's model loop and held by its native project."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.types import SourceInput
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSourceFile
from sqlbuild.compiler.scopes.types import ResourceKind
from sqlbuild.spec.contracts.models import SettingsConfig, SourceEntry


def attach_sources(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
    effective_settings: SettingsConfig,
    no_sql_validation: bool,
) -> tuple[SourceInput, ...]:
    """Expand and validate every discovered source in declaration order."""

    rows: list[tuple[str, DiscoveredSourceFile, SourceEntry]] = []
    for source_file in discovered_inputs.source_files:
        rows.extend(
            (str(source_file.file_path), source_file, entry) for entry in source_file.source_entries
        )
    return tuple(
        native_project.attach_sources(
            rows,
            (
                discovered_inputs.project_config.defaults.contract,
                effective_settings.sql_analysis and not no_sql_validation,
                ResourceKind.SOURCE,
            ),
        )
    )
