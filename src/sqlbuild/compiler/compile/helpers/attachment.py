"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.templating import (
    expand_effective_vars,
    expand_template_data,
)
from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    CompileModelInput,
    CompileSeedInput,
    CompileSourceInput,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlModelFile,
)
from sqlbuild.spec.models.project import (
    DefaultsConfig,
    EnvironmentConfig,
    LocalConfig,
    ProjectConfig,
)
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


def build_model_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    effective_vars: dict[str, str],
    environment_config: EnvironmentConfig | None,
) -> tuple[CompileModelInput, ...]:
    """Attach schema metadata to discovered model files."""

    model_inputs: list[CompileModelInput] = []
    model_file: DiscoveredSqlModelFile
    for model_file in discovered_inputs.model_files:
        matched_path_default: str | None = find_matching_path_default(
            model_file=model_file,
            path_defaults=discovered_inputs.project_config.path_defaults,
        )
        effective_config: CompileModelConfig = build_model_config(
            defaults=discovered_inputs.project_config.defaults,
            path_defaults=discovered_inputs.project_config.path_defaults,
            matched_path_default=matched_path_default,
            model_header_values=model_file.header_values,
            effective_vars=effective_vars,
            environment_config=environment_config,
        )
        schema_match: tuple[SchemaModelEntry, DiscoveredSchemaFile] | None = (
            find_schema_model_match(
                model_file=model_file,
                schema_files=discovered_inputs.schema_files,
            )
        )
        if schema_match is None:
            model_inputs.append(CompileModelInput(model_file=model_file, config=effective_config))
            continue

        schema_entry: SchemaModelEntry = schema_match[0]
        schema_file: DiscoveredSchemaFile = schema_match[1]
        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
                config=effective_config,
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


def resolve_environment_name(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    selected_environment: str | None,
) -> str | None:
    """Resolve the effective environment name for compile input building."""

    environment_name: str | None = selected_environment
    if environment_name is None:
        environment_name = local_config.environment
    if environment_name is None:
        environment_name = project_config.default_environment
    if environment_name is None:
        return None
    if environment_name not in project_config.environments:
        raise CompileInputError(f"Unknown environment '{environment_name}'")
    return environment_name


def build_effective_connection(
    *,
    project_config: ProjectConfig,
    environment_config: EnvironmentConfig | None,
    effective_vars: dict[str, str],
) -> dict[str, object]:
    """Merge base project connection with the selected environment overrides."""

    connection: dict[str, object] = dict(project_config.connection)
    if environment_config is not None:
        connection.update(environment_config.connection)
    return cast(
        dict[str, object],
        expand_template_data(
            connection,
            variables=effective_vars,
            context_values={},
            context_label="effective connection",
            allow_context=False,
            allowed_context_keys=tuple(),
        ),
    )


def build_effective_vars(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    environment_config: EnvironmentConfig | None,
    cli_vars: dict[str, str],
) -> dict[str, str]:
    """Merge effective vars using the locked precedence order."""

    values: dict[str, str] = dict(project_config.vars)
    if environment_config is not None:
        values.update(environment_config.vars)
    values.update(local_config.vars)
    values.update(cli_vars)
    return expand_effective_vars(values)


def build_model_config(
    *,
    defaults: DefaultsConfig,
    path_defaults: dict[str, dict[str, object]],
    matched_path_default: str | None,
    model_header_values: dict[str, object],
    effective_vars: dict[str, str],
    environment_config: EnvironmentConfig | None,
) -> CompileModelConfig:
    """Build the pre-semantic effective model config layers."""

    values: dict[str, object] = project_defaults_to_mapping(defaults)
    if matched_path_default is not None:
        values.update(path_defaults[matched_path_default])
    values.update(model_header_values)
    expanded_values: dict[str, object] = cast(
        dict[str, object],
        expand_template_data(
            values,
            variables=effective_vars,
            context_values={},
            context_label="model config",
            allow_context=False,
            allowed_context_keys=tuple(),
        ),
    )
    apply_environment_database_schema_overrides(
        values=expanded_values,
        effective_vars=effective_vars,
        environment_config=environment_config,
    )
    return CompileModelConfig(values=expanded_values, matched_path_default=matched_path_default)


def apply_environment_database_schema_overrides(
    *,
    values: dict[str, object],
    effective_vars: dict[str, str],
    environment_config: EnvironmentConfig | None,
) -> None:
    """Apply environment database/schema overrides using the logical config as CTX."""

    if environment_config is None:
        return

    raw_database: object | None = values.get("database")
    raw_schema: object | None = values.get("schema")
    logical_database: str | None = None if not isinstance(raw_database, str) else raw_database
    logical_schema: str | None = None if not isinstance(raw_schema, str) else raw_schema
    context_values: dict[str, str | None] = {
        "database": logical_database,
        "schema": logical_schema,
    }

    if environment_config.database is not None and environment_config.database != "preserve":
        values["database"] = expand_template_data(
            environment_config.database,
            variables=effective_vars,
            context_values=context_values,
            context_label="environment database",
            allow_context=True,
            allowed_context_keys=("database", "schema"),
        )
    if environment_config.schema is not None and environment_config.schema != "preserve":
        values["schema"] = expand_template_data(
            environment_config.schema,
            variables=effective_vars,
            context_values=context_values,
            context_label="environment schema",
            allow_context=True,
            allowed_context_keys=("database", "schema"),
        )


def find_matching_path_default(
    *,
    model_file: DiscoveredSqlModelFile,
    path_defaults: dict[str, dict[str, object]],
) -> str | None:
    """Return the nearest matching path_defaults key for a model file."""

    relative_path: Path = model_file.relative_path
    best_match: str | None = None
    best_length: int = -1

    path_key: str
    for path_key in path_defaults:
        path_key_parts: tuple[str, ...] = Path(path_key).parts
        if relative_path.parts[: len(path_key_parts)] != path_key_parts:
            continue
        if len(path_key_parts) > best_length:
            best_match = path_key
            best_length = len(path_key_parts)
    return best_match


def project_defaults_to_mapping(defaults: DefaultsConfig) -> dict[str, object]:
    """Convert project defaults into a sparse mapping for pre-semantic overlay."""

    values: dict[str, object] = {}
    if defaults.materialized is not None:
        values["materialized"] = defaults.materialized
    if defaults.database is not None:
        values["database"] = defaults.database
    if defaults.schema is not None:
        values["schema"] = defaults.schema
    if defaults.incremental_strategy is not None:
        values["incremental_strategy"] = defaults.incremental_strategy
    if defaults.incremental_mode is not None:
        values["incremental_mode"] = defaults.incremental_mode
    if defaults.lookback is not None:
        values["lookback"] = defaults.lookback
    if defaults.batch_size is not None:
        values["batch_size"] = defaults.batch_size
    if defaults.query_change_backfill is not None:
        values["query_change_backfill"] = defaults.query_change_backfill
    if defaults.schema_change_backfill:
        values["schema_change_backfill"] = defaults.schema_change_backfill
    if defaults.row_diff_exclude_columns:
        values["row_diff_exclude_columns"] = defaults.row_diff_exclude_columns
    return values


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
