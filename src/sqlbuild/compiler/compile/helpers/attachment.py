"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlbuild.compiler.compile.constants import MACRO_CALL_PATTERN
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.macros import (
    expand_sql_macros,
    load_project_macros,
)
from sqlbuild.compiler.compile.helpers.templating import (
    expand_effective_vars,
    expand_template_data,
)
from sqlbuild.compiler.compile.models import (
    CompileAuditInput,
    CompileModelConfig,
    CompileModelInput,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlTestInput,
    LoadedMacro,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
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
    effective_environment_name: str | None,
    run_id: str,
) -> tuple[CompileModelInput, ...]:
    """Attach schema metadata to discovered model files."""

    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
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
            model_name=model_file.file_path.stem,
            effective_environment_name=effective_environment_name,
            run_id=run_id,
        )
        expanded_query_sql: str = expand_sql_macros(
            sql=model_file.query_sql,
            file_path=model_file.file_path,
            loaded_macros=loaded_macros,
        )
        expanded_config: CompileModelConfig = CompileModelConfig(
            values=expand_model_hook_macros(
                values=effective_config.values,
                file_path=model_file.file_path,
                loaded_macros=loaded_macros,
            ),
            matched_path_default=effective_config.matched_path_default,
        )
        schema_match: tuple[SchemaModelEntry, DiscoveredSchemaFile] | None = (
            find_schema_model_match(
                model_file=model_file,
                schema_files=discovered_inputs.schema_files,
            )
        )
        if schema_match is None:
            model_inputs.append(
                CompileModelInput(
                    model_file=model_file,
                    config=expanded_config,
                    query_sql=expanded_query_sql,
                )
            )
            continue

        schema_entry: SchemaModelEntry = schema_match[0]
        schema_file: DiscoveredSchemaFile = schema_match[1]
        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
                config=expanded_config,
                query_sql=expanded_query_sql,
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


def build_test_inputs(
    discovered_inputs: DiscoveredProjectInputs,
) -> tuple[CompileSqlTestInput, ...]:
    """Build compile-time test inputs from discovered SQL-native test blocks."""

    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
    test_inputs: list[CompileSqlTestInput] = []
    test_file: DiscoveredSqlTestFile
    for test_file in discovered_inputs.test_files:
        test_block: DiscoveredSqlTestBlock
        for test_block in test_file.blocks:
            test_inputs.append(
                CompileSqlTestInput(
                    test_file=test_file,
                    test_block=test_block,
                    sql_body=expand_sql_macros(
                        sql=test_block.sql_body,
                        file_path=test_file.file_path,
                        loaded_macros=loaded_macros,
                    ),
                )
            )
    return tuple(test_inputs)


def build_audit_inputs(
    discovered_inputs: DiscoveredProjectInputs,
) -> tuple[CompileAuditInput, ...]:
    """Build compile-time audit inputs from discovered SQL audit blocks."""

    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
    audit_inputs: list[CompileAuditInput] = []
    audit_file: DiscoveredAuditFile
    for audit_file in discovered_inputs.audit_files:
        audit_block: DiscoveredAuditBlock
        for audit_block in audit_file.blocks:
            audit_inputs.append(
                CompileAuditInput(
                    audit_file=audit_file,
                    audit_block=audit_block,
                    sql_body=expand_sql_macros(
                        sql=audit_block.sql_body,
                        file_path=audit_file.file_path,
                        loaded_macros=loaded_macros,
                    ),
                )
            )
    return tuple(audit_inputs)


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
            preserve_context_tokens=False,
            preserve_unknown_context=False,
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
    model_name: str,
    effective_environment_name: str | None,
    run_id: str,
) -> CompileModelConfig:
    """Build the pre-semantic effective model config layers."""

    layered_values: dict[str, object] = build_layered_model_values(
        defaults=defaults,
        path_defaults=path_defaults,
        matched_path_default=matched_path_default,
        model_header_values=model_header_values,
    )
    early_resolved_values: dict[str, object] = resolve_early_model_templates(
        values=layered_values,
        effective_vars=effective_vars,
        effective_environment_name=effective_environment_name,
        run_id=run_id,
    )
    model_resolved_values: dict[str, object] = resolve_model_context_templates(
        values=early_resolved_values,
        model_name=model_name,
        effective_environment_name=effective_environment_name,
        run_id=run_id,
    )
    model_resolved_values = resolve_model_context_templates(
        values=model_resolved_values,
        model_name=model_name,
        effective_environment_name=effective_environment_name,
        run_id=run_id,
    )
    apply_environment_database_schema_overrides(
        values=model_resolved_values,
        effective_vars=effective_vars,
        environment_config=environment_config,
        model_context_values=build_model_context_values(
            values=model_resolved_values,
            model_name=model_name,
            effective_environment_name=effective_environment_name,
            run_id=run_id,
            include_target_values=False,
        ),
    )
    target_resolved_values: dict[str, object] = resolve_target_context_templates(
        values=model_resolved_values,
        model_name=model_name,
        effective_environment_name=effective_environment_name,
        run_id=run_id,
    )
    validate_model_config_has_no_macros(values=target_resolved_values)
    return CompileModelConfig(
        values=target_resolved_values, matched_path_default=matched_path_default
    )


def expand_model_hook_macros(
    *,
    values: dict[str, object],
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
) -> dict[str, object]:
    """Expand macros only within executable hook SQL strings."""

    expanded_values: dict[str, object] = dict(values)
    hook_key: str
    for hook_key in ("pre_hook", "post_hook"):
        raw_hook_value: object | None = expanded_values.get(hook_key)
        if raw_hook_value is None:
            continue
        expanded_values[hook_key] = expand_sql_macros_in_value(
            value=raw_hook_value,
            file_path=file_path,
            loaded_macros=loaded_macros,
        )
    return expanded_values


def expand_sql_macros_in_value(
    *, value: object, file_path: Path, loaded_macros: dict[str, LoadedMacro]
) -> object:
    """Recursively expand macros inside supported SQL hook container shapes."""

    if isinstance(value, str):
        return expand_sql_macros(sql=value, file_path=file_path, loaded_macros=loaded_macros)
    if isinstance(value, list):
        return [
            expand_sql_macros_in_value(
                value=item,
                file_path=file_path,
                loaded_macros=loaded_macros,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            expand_sql_macros_in_value(
                value=item,
                file_path=file_path,
                loaded_macros=loaded_macros,
            )
            for item in value
        )
    return value


def validate_model_config_has_no_macros(*, values: dict[str, object]) -> None:
    """Reject macro calls in declarative model config while allowing hook SQL strings."""

    validate_no_macros_in_config_value(value=values, path=())


def validate_no_macros_in_config_value(*, value: object, path: tuple[str, ...]) -> None:
    """Recursively reject macro calls outside hook fields."""

    if path and path[0] in {"pre_hook", "post_hook"}:
        return
    if isinstance(value, str):
        if MACRO_CALL_PATTERN.search(value) is not None:
            field_path: str = ".".join(path) if path else "<root>"
            raise CompileInputError(f"model config field '{field_path}' does not allow macros")
        return
    if isinstance(value, dict):
        key: object
        item_value: object
        for key, item_value in value.items():
            if isinstance(key, str):
                validate_no_macros_in_config_value(value=item_value, path=(*path, key))
        return
    if isinstance(value, list | tuple):
        item: object
        for item in value:
            validate_no_macros_in_config_value(value=item, path=path)


def build_layered_model_values(
    *,
    defaults: DefaultsConfig,
    path_defaults: dict[str, dict[str, object]],
    matched_path_default: str | None,
    model_header_values: dict[str, object],
) -> dict[str, object]:
    """Layer project defaults, path defaults, and MODEL header values."""

    values: dict[str, object] = project_defaults_to_mapping(defaults)
    if matched_path_default is not None:
        values.update(path_defaults[matched_path_default])
    values.update(model_header_values)
    return values


def resolve_early_model_templates(
    *,
    values: dict[str, object],
    effective_vars: dict[str, str],
    effective_environment_name: str | None,
    run_id: str,
) -> dict[str, object]:
    """Resolve `${name}`, `${ENV:...}`, and early `run.*` model templates."""

    return cast(
        dict[str, object],
        expand_template_data(
            values,
            variables=effective_vars,
            context_values=build_run_context_values(
                effective_environment_name=effective_environment_name,
                run_id=run_id,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=True,
        ),
    )


def resolve_model_context_templates(
    *,
    values: dict[str, object],
    model_name: str,
    effective_environment_name: str | None,
    run_id: str,
) -> dict[str, object]:
    """Resolve model-bound `CTX` values once logical model identity is known."""

    return cast(
        dict[str, object],
        expand_template_data(
            values,
            variables={},
            context_values=build_model_context_values(
                values=values,
                model_name=model_name,
                effective_environment_name=effective_environment_name,
                run_id=run_id,
                include_target_values=False,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=True,
        ),
    )


def resolve_target_context_templates(
    *,
    values: dict[str, object],
    model_name: str,
    effective_environment_name: str | None,
    run_id: str,
) -> dict[str, object]:
    """Resolve late `target.*` values after environment overrides finalize naming."""

    return cast(
        dict[str, object],
        expand_template_data(
            values,
            variables={},
            context_values=build_model_context_values(
                values=values,
                model_name=model_name,
                effective_environment_name=effective_environment_name,
                run_id=run_id,
                include_target_values=True,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        ),
    )


def build_model_context_values(
    *,
    values: dict[str, object],
    model_name: str,
    effective_environment_name: str | None,
    run_id: str,
    include_target_values: bool,
) -> dict[str, str | None]:
    """Build the currently available model-scoped CTX values."""

    raw_database: object | None = values.get("database")
    raw_schema: object | None = values.get("schema")
    raw_alias: object | None = values.get("alias")
    logical_database: str | None = None if not isinstance(raw_database, str) else raw_database
    logical_schema: str | None = None if not isinstance(raw_schema, str) else raw_schema
    logical_alias: str = model_name if not isinstance(raw_alias, str) else raw_alias
    context_values: dict[str, str | None] = {
        **build_run_context_values(
            effective_environment_name=effective_environment_name,
            run_id=run_id,
        ),
        "model.name": model_name,
        "model.database": logical_database,
        "model.schema": logical_schema,
        "model.alias": logical_alias,
    }
    if not include_target_values:
        return context_values

    target_database: str | None = logical_database
    target_schema: str | None = logical_schema
    target_table: str = logical_alias
    target_qualified: str | None = None
    if target_database is not None and target_schema is not None:
        target_qualified = f"{target_database}.{target_schema}.{target_table}"
    elif target_schema is not None:
        target_qualified = f"{target_schema}.{target_table}"
    context_values["target.database"] = target_database
    context_values["target.schema"] = target_schema
    context_values["target.table"] = target_table
    context_values["target.qualified"] = target_qualified
    return context_values


def build_run_context_values(
    *, effective_environment_name: str | None, run_id: str
) -> dict[str, str | None]:
    """Build the compile-time CTX values known before resource-specific resolution."""

    return {
        "run.id": run_id,
        "run.environment": effective_environment_name,
    }


def apply_environment_database_schema_overrides(
    *,
    values: dict[str, object],
    effective_vars: dict[str, str],
    environment_config: EnvironmentConfig | None,
    model_context_values: dict[str, str | None],
) -> None:
    """Apply environment database/schema overrides using the logical config as CTX."""

    if environment_config is None:
        return

    if environment_config.database is not None and environment_config.database != "preserve":
        values["database"] = expand_template_data(
            environment_config.database,
            variables=effective_vars,
            context_values=model_context_values,
            context_label="environment database",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    if environment_config.schema is not None and environment_config.schema != "preserve":
        values["schema"] = expand_template_data(
            environment_config.schema,
            variables=effective_vars,
            context_values=model_context_values,
            context_label="environment schema",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )


def resolve_run_id(*, selected_run_id: str | None) -> str:
    """Resolve a stable compile invocation id."""

    if selected_run_id is not None:
        return selected_run_id
    timestamp_prefix: str = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    unique_suffix: str = uuid4().hex[:6]
    return f"{timestamp_prefix}_{unique_suffix}"


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
