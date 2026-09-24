"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

from sqlbuild.compiler.auditing.main._parse_audit_instances import parse_audit_instances
from sqlbuild.compiler.authored_values.main._optional_named_string import optional_named_string
from sqlbuild.compiler.compile._helpers.audit_factories.core import (
    merge_validated_model_audits,
    parse_model_header_audit_factories,
)
from sqlbuild.compiler.compile._helpers.config.dynamic_columns import (
    parse_dynamic_column_families,
)
from sqlbuild.compiler.compile._helpers.render.templating import (
    contains_template_data,
)
from sqlbuild.compiler.compile.constants import (
    MACRO_CALL_PATTERN,
    MODEL_AUDIT_OVERRIDE_KEYS,
    MODEL_HEADER_METADATA_KEYS,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CachedModelHeaderColumns,
    CompileModelConfig,
    CompileModelInput,
    IdentityPresenceCache,
    ModelHeaderColumnCache,
)
from sqlbuild.compiler.discovery.main._model_schema_columns import parse_schema_columns
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditFactory,
    DiscoveredSchemaFile,
    DiscoveredSqlModelFile,
    ModelSchemaDeclaration,
)
from sqlbuild.compiler.path_defaults.main._select import select_path_default
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    SchemaAuditInstance,
    SchemaColumn,
    SchemaDynamicColumnFamily,
    SchemaModelEntry,
    SettingsConfig,
    SourceLocation,
)

_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})


def _contains_template_data_cached(*, value: object, cache: IdentityPresenceCache | None) -> bool:
    if cache is None or not isinstance(value, dict | list | tuple):
        return contains_template_data(value)
    cached: bool | None = cache.get(value)
    if cached is not None:
        return cached
    if isinstance(value, dict):
        result: bool = any(
            _contains_template_data_cached(value=item, cache=cache) for item in value.values()
        )
    else:
        result = any(_contains_template_data_cached(value=item, cache=cache) for item in value)
    cache.put(value=value, result=result)
    return result


def _contains_model_config_macro_cached(
    *, values: dict[str, object], cache: IdentityPresenceCache | None
) -> bool:
    return any(
        _contains_macro_data_cached(value=value, cache=cache)
        for key, value in values.items()
        if key not in _MODEL_HOOK_KEYS
    )


def _contains_macro_data_cached(*, value: object, cache: IdentityPresenceCache | None) -> bool:
    if isinstance(value, str):
        return MACRO_CALL_PATTERN.search(value) is not None
    if not isinstance(value, dict | list | tuple):
        return False
    if cache is not None:
        cached: bool | None = cache.get(value)
        if cached is not None:
            return cached
    if isinstance(value, dict):
        result: bool = any(
            _contains_macro_data_cached(value=item, cache=cache) for item in value.values()
        )
    else:
        result = any(_contains_macro_data_cached(value=item, cache=cache) for item in value)
    if cache is not None:
        cache.put(value=value, result=result)
    return result


def validate_no_macros_in_config_value(*, value: object, path: tuple[str, ...]) -> None:
    """Recursively reject macro calls outside hook fields."""

    if path and path[0] in _MODEL_HOOK_KEYS:
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
        values = _merged_with_tag_union(base=values, overlay=path_defaults[matched_path_default])
    return _merged_with_tag_union(base=values, overlay=model_header_values)


def _merged_with_tag_union(
    *, base: dict[str, object], overlay: dict[str, object]
) -> dict[str, object]:
    """Merge overlay into a copy of base, preserving special config merge semantics."""

    overlay_tags: object | None = overlay.get("tags")
    base_tags: object | None = base.get("tags")
    overlay_row_diff_exclude_columns: object | None = overlay.get("row_diff_exclude_columns")
    base_row_diff_exclude_columns: object | None = base.get("row_diff_exclude_columns")
    overlay_row_diff_tolerances: object | None = overlay.get("row_diff_tolerances")
    base_row_diff_tolerances: object | None = base.get("row_diff_tolerances")
    result: dict[str, object] = dict(base)
    result.update(overlay)
    if overlay_tags is not None and base_tags is not None:
        merged: list[str] = list(_as_string_list(base_tags))
        tag: str
        for tag in _as_string_list(overlay_tags):
            if tag not in merged:
                merged.append(tag)
        result["tags"] = merged
    if overlay_row_diff_exclude_columns is not None and base_row_diff_exclude_columns is not None:
        result["row_diff_exclude_columns"] = tuple(
            _merge_string_sequence(
                base=base_row_diff_exclude_columns,
                overlay=overlay_row_diff_exclude_columns,
            )
        )
    if overlay_row_diff_tolerances is not None and base_row_diff_tolerances is not None:
        result["row_diff_tolerances"] = _merge_row_diff_tolerances_mapping(
            base=base_row_diff_tolerances,
            overlay=overlay_row_diff_tolerances,
        )
    return result


def _merge_string_sequence(*, base: object, overlay: object) -> list[str]:
    """Merge string sequence-like values while preserving first occurrence order."""

    merged: list[str] = list(_as_string_list(base))
    value: str
    for value in _as_string_list(overlay):
        if value not in merged:
            merged.append(value)
    return merged


def _merge_row_diff_tolerances_mapping(*, base: object, overlay: object) -> object:
    """Deep merge row diff tolerance mappings by section and rule key."""

    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return overlay

    base_mapping: dict[str, object] = cast(dict[str, object], base)
    overlay_mapping: dict[str, object] = cast(dict[str, object], overlay)
    merged: dict[str, object] = dict(base_mapping)
    section: str
    for section in ("by_type", "by_column"):
        base_section: object | None = base_mapping.get(section)
        overlay_section: object | None = overlay_mapping.get(section)
        if overlay_section is None:
            continue
        if isinstance(base_section, dict) and isinstance(overlay_section, dict):
            merged[section] = {**base_section, **overlay_section}
        else:
            merged[section] = overlay_section
    key: object
    value: object
    for key, value in overlay_mapping.items():
        if isinstance(key, str) and key not in MODEL_AUDIT_OVERRIDE_KEYS:
            merged[key] = value
    return merged


def _as_string_list(value: object) -> list[str]:
    """Coerce a tags value to a list of strings."""

    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return []


def _validate_model_header_tags(
    *,
    model_header_values: dict[str, object],
    model_name: str,
) -> None:
    """Validate that tags in a MODEL header is a list of strings."""

    raw_tags: object | None = model_header_values.get("tags")
    if raw_tags is None:
        return
    if not isinstance(raw_tags, list):
        raise CompileInputError(f"model '{model_name}' tags must be a list")
    item: object
    for item in raw_tags:
        if not isinstance(item, str):
            raise CompileInputError(f"model '{model_name}' tags entries must be strings")


def build_model_header_schema_entry(
    *,
    model_name: str,
    model_header_values: dict[str, object],
    file_path: Path,
    column_locations: dict[str, SourceLocation] | None = None,
    model_schema_columns: tuple[SchemaColumn, ...] | None = None,
    model_schema_name: str | None = None,
    model_schema_description: str | None = None,
    audit_factories: tuple[DiscoveredAuditFactory, ...] = (),
    column_cache: ModelHeaderColumnCache | None = None,
) -> SchemaModelEntry | None:
    """Normalize model-owned MODEL(...) metadata into the existing schema entry shape."""

    raw_description: object | None = model_header_values.get("description")
    raw_columns: object | None = model_header_values.get("columns")
    raw_dynamic_columns: object | None = model_header_values.get("dynamic_columns")
    raw_audits: object | None = model_header_values.get("audits")
    raw_audit_factories: object | None = model_header_values.get("audit_factories")
    if (
        raw_description is None
        and raw_columns is None
        and raw_dynamic_columns is None
        and raw_audits is None
        and raw_audit_factories is None
        and model_schema_columns is None
    ):
        return None

    model_description: str | None = optional_named_string(
        raw_value=raw_description,
        file_path=file_path,
        label="model",
        key="description",
        error_class=CompileInputError,
    )
    description: str | None = model_description or model_schema_description
    local_columns: tuple[SchemaColumn, ...] = _parse_model_header_columns(
        raw_columns=raw_columns,
        file_path=file_path,
        column_locations=column_locations or {},
        column_cache=column_cache,
    )
    columns: tuple[SchemaColumn, ...] = _merge_model_schema_columns(
        model_name=model_name,
        file_path=file_path,
        model_schema_columns=model_schema_columns,
        local_columns=local_columns,
    )
    dynamic_columns: tuple[SchemaDynamicColumnFamily, ...] = parse_dynamic_column_families(
        raw_value=raw_dynamic_columns,
        model_name=model_name,
        file_path=file_path,
    )
    audits: tuple[SchemaAuditInstance, ...] = parse_audit_instances(
        raw_audits=raw_audits,
        file_path=file_path,
        label="model",
        error_class=CompileInputError,
        null_as_empty=True,
    )
    generated_audits: tuple[SchemaAuditInstance, ...] = parse_model_header_audit_factories(
        raw_audit_factories=raw_audit_factories,
        file_path=file_path,
        model_name=model_name,
        audit_factories=audit_factories,
    )
    audits = merge_validated_model_audits(
        direct_audits=audits,
        generated_audits=generated_audits,
        model_name=model_name,
        file_path=file_path,
    )
    type_enforcement: bool | None = (
        True if any(column.type is not None for column in columns) or dynamic_columns else None
    )
    return SchemaModelEntry(
        name=model_name,
        model_schema=model_schema_name,
        description=description,
        type_enforcement=type_enforcement,
        columns=columns,
        dynamic_columns=dynamic_columns,
        audits=audits,
    )


def strip_model_header_metadata_from_config(config: CompileModelConfig) -> CompileModelConfig:
    """Remove model metadata keys after they have been attached as schema metadata."""

    filtered_values: dict[str, object] = {
        key: value for key, value in config.values.items() if key not in MODEL_HEADER_METADATA_KEYS
    }
    if len(filtered_values) == len(config.values):
        return config
    return CompileModelConfig(
        values=filtered_values,
        model_header_keys=config.model_header_keys,
        matched_path_default=config.matched_path_default,
        logical_schema=config.logical_schema,
        layer_schema=config.layer_schema,
        logical_database=config.logical_database,
        time_travel_retention=config.time_travel_retention,
        table_type=config.table_type,
    )


def _parse_model_header_columns(
    *,
    raw_columns: object | None,
    file_path: Path,
    column_locations: dict[str, SourceLocation],
    column_cache: ModelHeaderColumnCache | None = None,
) -> tuple[SchemaColumn, ...]:
    if raw_columns is None or column_cache is None:
        return parse_schema_columns(
            raw_columns=raw_columns,
            file_path=file_path,
            label="model",
            error_class=CompileInputError,
            column_locations=column_locations,
        )
    cached: CachedModelHeaderColumns | None = column_cache.get(raw_columns)
    if cached is None:
        parsed: tuple[SchemaColumn, ...] = parse_schema_columns(
            raw_columns=raw_columns,
            file_path=file_path,
            label="model",
            error_class=CompileInputError,
            column_locations=column_locations,
        )
        cached = CachedModelHeaderColumns(
            raw_columns=raw_columns,
            columns=parsed,
            column_locations=column_locations,
        )
        column_cache.put(cached)
        return parsed
    if cached.column_locations is column_locations or (
        not cached.column_locations and not column_locations
    ):
        return cached.columns
    return tuple(
        _schema_column_at_location(
            column=column,
            location=column_locations.get(column.name),
        )
        for column in cached.columns
    )


def _schema_column_at_location(
    *, column: SchemaColumn, location: SourceLocation | None
) -> SchemaColumn:
    return SchemaColumn(
        name=column.name,
        type=column.type,
        nullable=column.nullable,
        description=column.description,
        meta=column.meta,
        audits=tuple(
            SchemaAuditInstance(
                definition_name=audit.definition_name,
                arguments=audit.arguments,
                name=audit.name,
                description=audit.description,
                severity=audit.severity,
                run_scope=audit.run_scope,
                always_run=audit.always_run,
                thresholds=audit.thresholds,
                minimum_samples=audit.minimum_samples,
                evidence_limit=audit.evidence_limit,
                location=location,
            )
            for audit in column.audits
        ),
        location=location,
    )


def _merge_model_schema_columns(
    *,
    model_name: str,
    file_path: Path,
    model_schema_columns: tuple[SchemaColumn, ...] | None,
    local_columns: tuple[SchemaColumn, ...],
) -> tuple[SchemaColumn, ...]:
    if model_schema_columns is None:
        return local_columns
    merged_named_columns: list[SchemaColumn] = list(model_schema_columns)
    named_index_by_name: dict[str, int] = {
        column.name.lower(): index for index, column in enumerate(model_schema_columns)
    }
    additional_columns: list[SchemaColumn] = []
    local_column: SchemaColumn
    for local_column in local_columns:
        named_index: int | None = named_index_by_name.get(local_column.name.lower())
        if named_index is None:
            additional_columns.append(local_column)
            continue
        named_column: SchemaColumn = merged_named_columns[named_index]
        _validate_model_schema_audit_augmentation(
            model_name=model_name,
            file_path=file_path,
            local_column=local_column,
            named_column=named_column,
        )
        merged_named_columns[named_index] = replace(
            named_column,
            audits=_merge_schema_audits(
                inherited_audits=named_column.audits,
                local_audits=local_column.audits,
            ),
        )
    return (*merged_named_columns, *additional_columns)


def _merge_schema_audits(
    *,
    inherited_audits: tuple[SchemaAuditInstance, ...],
    local_audits: tuple[SchemaAuditInstance, ...],
) -> tuple[SchemaAuditInstance, ...]:
    merged_audits: list[SchemaAuditInstance] = list(inherited_audits)
    audit: SchemaAuditInstance
    for audit in local_audits:
        if audit not in merged_audits:
            merged_audits.append(audit)
    return tuple(merged_audits)


def _validate_model_schema_audit_augmentation(
    *,
    model_name: str,
    file_path: Path,
    local_column: SchemaColumn,
    named_column: SchemaColumn,
) -> None:
    named_origin: str = (
        f"{named_column.location.path}:{named_column.location.line}"
        if named_column.location is not None
        else "the named schema"
    )
    overridden_fields: list[str] = []
    if local_column.type is not None:
        overridden_fields.append("type")
    if local_column.nullable is not None:
        overridden_fields.append("nullable")
    if local_column.description is not None:
        overridden_fields.append("description")
    if overridden_fields:
        raise CompileInputError(
            f"model '{model_name}' in {file_path} cannot override "
            f"{', '.join(overridden_fields)} for named-schema column '{local_column.name}' from "
            f"{named_origin}; only audit augmentation is supported"
        )
    if not local_column.audits:
        raise CompileInputError(
            f"model '{model_name}' in {file_path} redeclares named-schema column "
            f"'{local_column.name}' from {named_origin} without audits; only audit augmentation "
            "is supported"
        )


def _resolve_model_schema(
    *,
    values: dict[str, object],
    model_name: str,
    public_model_schemas: dict[str, ModelSchemaDeclaration],
) -> ModelSchemaDeclaration | None:
    raw_name: object | None = values.get("model_schema")
    if raw_name is None:
        return None
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise CompileInputError(f"model '{model_name}': model_schema must be a non-empty string")
    declaration: ModelSchemaDeclaration | None = public_model_schemas.get(raw_name)
    if declaration is None:
        available: str = ", ".join(sorted(public_model_schemas)) or "none"
        raise CompileInputError(
            f"model '{model_name}' references unknown model_schema '{raw_name}'; "
            f"available schemas: {available}"
        )
    return declaration


def _merge_schema_tags(
    *, config: CompileModelConfig, schema_entry: SchemaModelEntry
) -> CompileModelConfig:
    """Union schema.yml tags into model config values."""

    if not schema_entry.tags:
        return config
    merged_values: dict[str, object] = _merged_with_tag_union(
        base=dict(config.values),
        overlay={"tags": list(schema_entry.tags)},
    )
    return CompileModelConfig(
        values=merged_values,
        model_header_keys=config.model_header_keys,
        matched_path_default=config.matched_path_default,
        logical_schema=config.logical_schema,
        layer_schema=config.layer_schema,
        logical_database=config.logical_database,
        time_travel_retention=config.time_travel_retention,
        table_type=config.table_type,
    )


def find_matching_path_default(
    *,
    model_file: DiscoveredSqlModelFile,
    path_defaults: dict[str, dict[str, object]],
) -> str | None:
    """Return the nearest matching path_defaults key for a model file."""

    return select_path_default(
        model_path=str(model_file.relative_path),
        path_keys=tuple(path_defaults),
    ).selected_key


def project_defaults_to_mapping(defaults: DefaultsConfig) -> dict[str, object]:
    """Convert project defaults into a sparse mapping for pre-semantic overlay."""

    values: dict[str, object] = {}
    if defaults.materialized is not None:
        values["materialized"] = defaults.materialized
    if defaults.database is not None:
        values["database"] = defaults.database
    if defaults.schema is not None:
        values["schema"] = defaults.schema
    if defaults.contract is not None:
        values["contract"] = defaults.contract
    if defaults.incremental_strategy is not None:
        values["incremental_strategy"] = defaults.incremental_strategy
    if defaults.incremental_mode is not None:
        values["incremental_mode"] = defaults.incremental_mode
    if defaults.microbatch_strategy is not None:
        values["microbatch_strategy"] = defaults.microbatch_strategy
    if defaults.cursor_watermark_mode is not None:
        values["cursor_watermark_mode"] = defaults.cursor_watermark_mode
    if defaults.merge_exclude_columns:
        values["merge_exclude_columns"] = defaults.merge_exclude_columns
    if defaults.full_refresh is not None:
        values["full_refresh"] = defaults.full_refresh
    if defaults.append_cursor_inclusive is not None:
        values["append_cursor_inclusive"] = defaults.append_cursor_inclusive
    if defaults.cursor_start is not None:
        values["cursor_start"] = defaults.cursor_start
    if defaults.cursor_end is not None:
        values["cursor_end"] = defaults.cursor_end
    if defaults.cursor_start_max_ahead is not None:
        values["cursor_start_max_ahead"] = defaults.cursor_start_max_ahead
    if defaults.cursor_start_max_action is not None:
        values["cursor_start_max_action"] = defaults.cursor_start_max_action
    if defaults.cursor_future_max_distance is not None:
        values["cursor_future_max_distance"] = defaults.cursor_future_max_distance
    if defaults.cursor_future_action is not None:
        values["cursor_future_action"] = defaults.cursor_future_action
    if defaults.lookback is not None:
        values["lookback"] = defaults.lookback
    if defaults.batch_size is not None:
        values["batch_size"] = defaults.batch_size
    if defaults.batch_concurrency is not None:
        values["batch_concurrency"] = defaults.batch_concurrency
    if defaults.max_microbatches is not None:
        values["max_microbatches"] = defaults.max_microbatches
    if defaults.unaccounted_partition_policy is not None:
        values["unaccounted_partition_policy"] = defaults.unaccounted_partition_policy
    if defaults.replay_on_change is not None:
        values["replay_on_change"] = defaults.replay_on_change
    if defaults.run_despite_unchanged is not None:
        values["run_despite_unchanged"] = defaults.run_despite_unchanged
    if defaults.row_diff_exclude_columns:
        values["row_diff_exclude_columns"] = defaults.row_diff_exclude_columns
    if defaults.row_diff_tolerances:
        values["row_diff_tolerances"] = defaults.row_diff_tolerances
    if defaults.row_diff_sample_rows is not None:
        values["row_diff_sample_rows"] = defaults.row_diff_sample_rows
    if defaults.row_diff_sample_seed is not None:
        values["row_diff_sample_seed"] = defaults.row_diff_sample_seed
    if defaults.tags:
        values["tags"] = list(defaults.tags)
    if defaults.pre_hooks is not None:
        values["pre_hooks"] = defaults.pre_hooks
    if defaults.post_hooks is not None:
        values["post_hooks"] = defaults.post_hooks
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


def _str_from_dict(*, values: dict[str, object], key: str) -> str | None:
    """Extract a string value from a dict."""

    raw: object | None = values.get(key)
    return raw if isinstance(raw, str) else None


def _bool_from_dict(*, values: dict[str, object], key: str) -> bool:
    raw: object | None = values.get(key)
    if raw is None:
        return False
    if not isinstance(raw, bool):
        raise CompileInputError(f"AUDIT() '{key}' must be a boolean")
    return raw


def _is_sql_validation_enabled(*, project_setting: bool, model_config: CompileModelConfig) -> bool:
    """Apply the per-model unified SQL analysis override to the project setting."""

    raw_analysis: object | None = model_config.values.get("sql_analysis")
    raw_legacy: object | None = model_config.values.get("sql_validation")
    if raw_analysis is not None and raw_legacy is not None and raw_analysis != raw_legacy:
        raise CompileInputError(
            "MODEL sql_analysis conflicts with legacy sql_validation",
            code="P003",
        )
    raw: object | None = raw_analysis if raw_analysis is not None else raw_legacy
    if isinstance(raw, bool):
        return raw
    return project_setting


def _model_sql_validation_gate(
    *,
    effective_settings: SettingsConfig,
    no_sql_validation: bool,
    model_config: CompileModelConfig,
) -> bool:
    """Apply the unified project/model/CLI SQL analysis gate."""

    return (
        effective_settings.sql_analysis
        and not no_sql_validation
        and _is_sql_validation_enabled(
            project_setting=effective_settings.sql_analysis,
            model_config=model_config,
        )
    )
