"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileModelInput, CompileSeedInput, CompileSourceInput
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlModelFile,
)
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


def build_model_inputs(discovered_inputs: DiscoveredProjectInputs) -> tuple[CompileModelInput, ...]:
    """Attach schema metadata to discovered model files."""

    model_inputs: list[CompileModelInput] = []
    model_file: DiscoveredSqlModelFile
    for model_file in discovered_inputs.model_files:
        schema_match: tuple[SchemaModelEntry, DiscoveredSchemaFile] | None = (
            find_schema_model_match(
                model_file=model_file,
                schema_files=discovered_inputs.schema_files,
            )
        )
        if schema_match is None:
            model_inputs.append(CompileModelInput(model_file=model_file))
            continue

        schema_entry: SchemaModelEntry = schema_match[0]
        schema_file: DiscoveredSchemaFile = schema_match[1]
        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
                schema_entry=schema_entry,
                schema_file=schema_file,
            )
        )

    validate_declared_schema_models_are_attached(
        model_inputs=tuple(model_inputs),
        schema_files=discovered_inputs.schema_files,
    )
    return tuple(model_inputs)


def build_seed_inputs(discovered_inputs: DiscoveredProjectInputs) -> tuple[CompileSeedInput, ...]:
    """Attach seed schema metadata to discovered seed files."""

    seed_schema_matches: dict[str, tuple[SchemaSeedEntry, DiscoveredSchemaFile]] = {}
    schema_file: DiscoveredSchemaFile
    for schema_file in discovered_inputs.schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            seed_schema_matches[seed_entry.name] = (seed_entry, schema_file)

    seed_inputs: list[CompileSeedInput] = []
    seed_file: DiscoveredSeedFile
    for seed_file in discovered_inputs.seed_files:
        if seed_file.file_path.suffix != ".csv":
            continue

        seed_name: str = seed_file.file_path.stem
        schema_match: tuple[SchemaSeedEntry, DiscoveredSchemaFile] | None = seed_schema_matches.get(
            seed_name
        )
        if schema_match is None:
            raise CompileInputError(
                f"Seed file {seed_file.relative_path} has no matching seed declaration in "
                "schema.yml"
            )

        seed_inputs.append(
            CompileSeedInput(
                seed_file=seed_file,
                schema_entry=schema_match[0],
                schema_file=schema_match[1],
            )
        )

    return tuple(seed_inputs)


def build_source_inputs(
    discovered_inputs: DiscoveredProjectInputs,
) -> tuple[CompileSourceInput, ...]:
    """Normalize discovered source declarations into one collection."""

    source_inputs: list[CompileSourceInput] = []
    source_file: DiscoveredSourceFile
    for source_file in discovered_inputs.source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            source_inputs.append(
                CompileSourceInput(
                    source_entry=source_entry,
                    source_file=source_file,
                )
            )
    return tuple(source_inputs)


def find_schema_model_match(
    *,
    model_file: DiscoveredSqlModelFile,
    schema_files: tuple[DiscoveredSchemaFile, ...],
) -> tuple[SchemaModelEntry, DiscoveredSchemaFile] | None:
    """Find the schema.yml model entry that applies to a discovered model file."""

    model_name: str = model_file.file_path.stem
    matching_entries: list[tuple[SchemaModelEntry, DiscoveredSchemaFile]] = []
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        schema_directory: Path = schema_file.relative_path.parent
        try:
            model_file.relative_path.relative_to(schema_directory)
        except ValueError:
            continue

        schema_entry: SchemaModelEntry
        for schema_entry in schema_file.model_entries:
            if schema_entry.name == model_name:
                matching_entries.append((schema_entry, schema_file))

    if not matching_entries:
        return None
    if len(matching_entries) > 1:
        matching_paths: str = ", ".join(
            str(schema_file.relative_path) for _, schema_file in matching_entries
        )
        raise CompileInputError(
            f"Model file {model_file.relative_path} matched multiple schema.yml declarations: "
            f"{matching_paths}"
        )
    return matching_entries[0]


def validate_declared_schema_models_are_attached(
    *,
    model_inputs: tuple[CompileModelInput, ...],
    schema_files: tuple[DiscoveredSchemaFile, ...],
) -> None:
    """Ensure every declared schema.yml model entry attaches within its directory scope."""

    attached_model_names: set[str] = {
        model_input.schema_entry.name
        for model_input in model_inputs
        if model_input.schema_entry is not None
    }
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        schema_entry: SchemaModelEntry
        for schema_entry in schema_file.model_entries:
            if schema_entry.name not in attached_model_names:
                raise CompileInputError(
                    f"schema.yml declaration for model '{schema_entry.name}' in "
                    f"{schema_file.relative_path} "
                    "does not match any discovered model file in that directory scope"
                )
