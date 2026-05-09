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
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
)
from sqlbuild.compiler.shared.constants import RESERVED_MODEL_NAMES
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


def validate_discovered_inputs(discovered_inputs: DiscoveredProjectInputs) -> None:
    """Validate cross-file conflicts across discovered project inputs."""

    _validate_unique_model_file_names(discovered_inputs.model_files)
    _validate_unique_scenario_file_names(discovered_inputs.scenario_files)
    _validate_unique_source_names(discovered_inputs.source_files)
    _validate_unique_schema_model_names(discovered_inputs.schema_files)
    _validate_unique_schema_seed_names(discovered_inputs.schema_files)
    _validate_unique_logical_relation_names(
        model_files=discovered_inputs.model_files,
        source_files=discovered_inputs.source_files,
        schema_files=discovered_inputs.schema_files,
    )
    _validate_declared_seed_files(
        schema_files=discovered_inputs.schema_files,
        seed_files=discovered_inputs.seed_files,
    )
    _validate_path_defaults_match_models(
        path_defaults=discovered_inputs.project_config.path_defaults,
        model_files=discovered_inputs.model_files,
    )


def _validate_unique_model_file_names(model_files: tuple[DiscoveredSqlModelFile, ...]) -> None:
    seen_names: dict[str, str] = {}
    model_file: DiscoveredSqlModelFile
    for model_file in model_files:
        model_name: str = model_file.file_path.stem
        if model_name in RESERVED_MODEL_NAMES:
            raise DiscoveryConflictError(
                f"Model name '{model_name}' in {model_file.relative_path} is reserved "
                "by SQLBuild for compiled output structure"
            )
        existing_path: str | None = seen_names.get(model_name)
        if existing_path is not None:
            raise DiscoveryConflictError(
                f"Duplicate model file name found for '{model_name}' in "
                f"{existing_path} and {model_file.relative_path}"
            )
        seen_names[model_name] = str(model_file.relative_path)


def _validate_unique_scenario_file_names(
    scenario_files: tuple[DiscoveredSqlScenarioFile, ...],
) -> None:
    seen_names: dict[str, str] = {}
    scenario_file: DiscoveredSqlScenarioFile
    for scenario_file in scenario_files:
        existing_path: str | None = seen_names.get(scenario_file.name)
        if existing_path is not None:
            raise DiscoveryConflictError(
                f"Duplicate scenario file name found for '{scenario_file.name}' in "
                f"{existing_path} and {scenario_file.relative_path}"
            )
        seen_names[scenario_file.name] = str(scenario_file.relative_path)


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
                    "Duplicate seed declaration found for "
                    f"'{seed_entry.name}' in {existing_path} and {schema_file.relative_path}"
                )
            seen_names[seed_entry.name] = str(schema_file.relative_path)


def _validate_unique_logical_relation_names(
    *,
    model_files: tuple[DiscoveredSqlModelFile, ...],
    source_files: tuple[DiscoveredSourceFile, ...],
    schema_files: tuple[DiscoveredSchemaFile, ...],
) -> None:
    seen_names: dict[str, tuple[str, str]] = {}
    model_file: DiscoveredSqlModelFile
    for model_file in model_files:
        seen_names[model_file.file_path.stem] = ("model", str(model_file.relative_path))

    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            _validate_logical_relation_name_is_available(
                seen_names=seen_names,
                name=source_entry.name,
                kind="source",
                path=str(source_file.relative_path),
            )

    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            _validate_logical_relation_name_is_available(
                seen_names=seen_names,
                name=seed_entry.name,
                kind="seed",
                path=str(schema_file.relative_path),
            )


def _validate_logical_relation_name_is_available(
    *, seen_names: dict[str, tuple[str, str]], name: str, kind: str, path: str
) -> None:
    existing_entry: tuple[str, str] | None = seen_names.get(name)
    if existing_entry is not None:
        raise DiscoveryConflictError(
            f"Logical relation name '{name}' is declared as both {existing_entry[0]} "
            f"in {existing_entry[1]} and {kind} in {path}"
        )
    seen_names[name] = (kind, path)


def _validate_declared_seed_files(
    *,
    schema_files: tuple[DiscoveredSchemaFile, ...],
    seed_files: tuple[DiscoveredSeedFile, ...],
) -> None:
    _validate_unique_seed_csv_names(seed_files)
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
            seed_file for seed_file in seed_files if seed_file.file_path.stem == seed_entry.name
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

    declared_names: set[str] = {seed_entry.name for seed_entry, _ in declared_seed_entries}
    seed_file: DiscoveredSeedFile
    for seed_file in seed_files:
        if seed_file.file_path.stem not in declared_names:
            raise SeedDiscoveryError(
                f"Seed CSV {seed_file.relative_path} has no matching declaration for seed "
                f"'{seed_file.file_path.stem}' under seeds/**/*.yml"
            )


def _validate_unique_seed_csv_names(seed_files: tuple[DiscoveredSeedFile, ...]) -> None:
    seen_paths: dict[str, Path] = {}
    seed_file: DiscoveredSeedFile
    for seed_file in seed_files:
        seed_name: str = seed_file.file_path.stem
        existing_path: Path | None = seen_paths.get(seed_name)
        if existing_path is not None:
            raise SeedDiscoveryError(
                f"Duplicate seed CSV name '{seed_name}' found: {existing_path}, "
                f"{seed_file.relative_path}. Seed CSV filenames must be unique under seeds/."
            )
        seen_paths[seed_name] = seed_file.relative_path


def _validate_seed_csv_header(
    *, seed_entry: SchemaSeedEntry, seed_file: DiscoveredSeedFile
) -> None:
    header_columns: tuple[str, ...] = _load_seed_csv_header(
        seed_file.file_path,
        delimiter=seed_entry.csv_settings.delimiter,
        quotechar=seed_entry.csv_settings.quotechar,
        escapechar=seed_entry.csv_settings.escapechar,
        doublequote=seed_entry.csv_settings.doublequote,
        skipinitialspace=seed_entry.csv_settings.skipinitialspace,
    )
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


def _load_seed_csv_header(
    file_path: Path,
    *,
    delimiter: str | None,
    quotechar: str | None,
    escapechar: str | None,
    doublequote: bool | None,
    skipinitialspace: bool | None,
) -> tuple[str, ...]:
    reader_kwargs: dict[str, object] = {}
    if delimiter is not None:
        reader_kwargs["delimiter"] = delimiter
    if quotechar is not None:
        reader_kwargs["quotechar"] = quotechar
    if escapechar is not None:
        reader_kwargs["escapechar"] = escapechar
    if doublequote is not None:
        reader_kwargs["doublequote"] = doublequote
    if skipinitialspace is not None:
        reader_kwargs["skipinitialspace"] = skipinitialspace

    with file_path.open("r", encoding="utf-8", newline="") as handle:
        try:
            header_row: list[str] = next(
                csv.reader(
                    handle,
                    delimiter=delimiter or ",",
                    quotechar=quotechar,
                    escapechar=escapechar,
                    doublequote=True if doublequote is None else doublequote,
                    skipinitialspace=False if skipinitialspace is None else skipinitialspace,
                )
            )
        except StopIteration:
            return ()
    return tuple(header_row)


def _validate_path_defaults_match_models(
    *,
    path_defaults: dict[str, dict[str, object]],
    model_files: tuple[DiscoveredSqlModelFile, ...],
) -> None:
    if not path_defaults:
        return
    model_paths: tuple[str, ...] = tuple(
        str(model_file.relative_path).removeprefix("models/") for model_file in model_files
    )
    model_folders: tuple[str, ...] = tuple(
        sorted(
            {
                str(Path(model_path).parent)
                for model_path in model_paths
                if str(Path(model_path).parent) != "."
            }
        )
    )
    path_key: str
    for path_key in path_defaults:
        path_key_parts: tuple[str, ...] = Path(path_key).parts
        if any(
            Path(model_path).parts[: len(path_key_parts)] == path_key_parts
            for model_path in model_paths
        ):
            continue
        known_folders: str = ", ".join(model_folders[:5]) if model_folders else "<none>"
        raise DiscoveryConflictError(
            f"path_defaults['{path_key}'] does not match any model paths. Known model folders "
            f"include: {known_folders}"
        )
