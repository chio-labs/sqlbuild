"""Cross-file discovery validation helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from sqlbuild.compiler.discovery.exceptions import DiscoveryConflictError, SeedDiscoveryError
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
)
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


def validate_discovered_inputs(discovered_inputs: DiscoveredProjectInputs) -> None:
    """Validate cross-file conflicts across discovered project inputs."""

    _validate_unique_source_names(discovered_inputs.source_files)
    _validate_unique_schema_model_names(discovered_inputs.schema_files)
    _validate_unique_schema_seed_names(discovered_inputs.schema_files)
    _validate_declared_seed_files(
        schema_files=discovered_inputs.schema_files,
        seed_files=discovered_inputs.seed_files,
    )


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


def _validate_declared_seed_files(
    *,
    schema_files: tuple[DiscoveredSchemaFile, ...],
    seed_files: tuple[DiscoveredSeedFile, ...],
) -> None:
    declared_seed_entries: list[tuple[SchemaSeedEntry, str]] = []
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            declared_seed_entries.append((seed_entry, str(schema_file.relative_path)))

    seed_entry_and_path: tuple[SchemaSeedEntry, str]
    for seed_entry_and_path in declared_seed_entries:
        seed_entry: SchemaSeedEntry = seed_entry_and_path[0]
        declaration_path: str = seed_entry_and_path[1]
        matching_seed_files: tuple[DiscoveredSeedFile, ...] = tuple(
            seed_file
            for seed_file in seed_files
            if seed_file.file_path.suffix == ".csv" and seed_file.file_path.stem == seed_entry.name
        )
        if not matching_seed_files:
            raise SeedDiscoveryError(
                "Seed declaration "
                f"'{seed_entry.name}' in {declaration_path} has no matching CSV file under seeds/"
            )
        if len(matching_seed_files) > 1:
            matching_paths: str = ", ".join(
                str(seed_file.relative_path) for seed_file in matching_seed_files
            )
            raise SeedDiscoveryError(
                f"Seed declaration '{seed_entry.name}' matches multiple CSV files: {matching_paths}"
            )

        _validate_seed_csv_header(seed_entry=seed_entry, seed_file=matching_seed_files[0])


def _validate_seed_csv_header(
    *, seed_entry: SchemaSeedEntry, seed_file: DiscoveredSeedFile
) -> None:
    header_columns: tuple[str, ...] = _load_seed_csv_header(seed_file.file_path)
    if not header_columns:
        raise SeedDiscoveryError(f"{seed_file.relative_path} must contain a CSV header row")

    seen_columns: set[str] = set()
    column_name: str
    for column_name in header_columns:
        if column_name in seen_columns:
            raise SeedDiscoveryError(
                f"{seed_file.relative_path} contains duplicate CSV header column '{column_name}'"
            )
        seen_columns.add(column_name)

    declared_columns: tuple[str, ...] = tuple(column.name for column in seed_entry.columns)
    if header_columns != declared_columns:
        raise SeedDiscoveryError(
            f"{seed_file.relative_path} header {header_columns} does not match "
            "declared seed columns "
            f"{declared_columns} for '{seed_entry.name}'"
        )


def _load_seed_csv_header(file_path: Path) -> tuple[str, ...]:
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        try:
            header_row: list[str] = next(csv.reader(handle))
        except StopIteration:
            return ()
    return tuple(header_row)
