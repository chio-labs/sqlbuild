"""Cross-file discovery validation helpers."""

from __future__ import annotations

from sqlbuild.compiler.discovery.exceptions import DiscoveryConflictError
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSourceFile,
)
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


def validate_discovered_inputs(discovered_inputs: DiscoveredProjectInputs) -> None:
    """Validate cross-file conflicts across discovered project inputs."""

    _validate_unique_source_names(discovered_inputs.source_files)
    _validate_unique_schema_model_names(discovered_inputs.schema_files)
    _validate_unique_schema_seed_names(discovered_inputs.schema_files)


def _validate_unique_source_names(source_files: tuple[DiscoveredSourceFile, ...]) -> None:
    seen_names: dict[str, str] = {}
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            existing_path: str | None = seen_names.get(source_entry.name)
            if existing_path is not None:
                raise DiscoveryConflictError(
                    "Duplicate source declaration found for "
                    f"'{source_entry.name}' in {existing_path} and {source_file.relative_path}"
                )
            seen_names[source_entry.name] = str(source_file.relative_path)


def _validate_unique_schema_model_names(schema_files: tuple[DiscoveredSchemaFile, ...]) -> None:
    seen_names: dict[str, str] = {}
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        model_entry: SchemaModelEntry
        for model_entry in schema_file.model_entries:
            existing_path: str | None = seen_names.get(model_entry.name)
            if existing_path is not None:
                raise DiscoveryConflictError(
                    "Duplicate schema.yml model declaration found for "
                    f"'{model_entry.name}' in {existing_path} and {schema_file.relative_path}"
                )
            seen_names[model_entry.name] = str(schema_file.relative_path)


def _validate_unique_schema_seed_names(schema_files: tuple[DiscoveredSchemaFile, ...]) -> None:
    seen_names: dict[str, str] = {}
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            existing_path: str | None = seen_names.get(seed_entry.name)
            if existing_path is not None:
                raise DiscoveryConflictError(
                    "Duplicate schema.yml seed declaration found for "
                    f"'{seed_entry.name}' in {existing_path} and {schema_file.relative_path}"
                )
            seen_names[seed_entry.name] = str(schema_file.relative_path)
