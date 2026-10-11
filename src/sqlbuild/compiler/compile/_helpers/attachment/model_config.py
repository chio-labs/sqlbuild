"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

import sys
import unicodedata
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.config.retention import resolve_time_travel_retention
from sqlbuild.compiler.compile._helpers.config.table_type import resolve_table_type
from sqlbuild.compiler.compile._helpers.render.templating import (
    record_template_reads,
)
from sqlbuild.compiler.compile.classes.unicode_environment import UnicodeEnvironment
from sqlbuild.compiler.compile.constants import (
    MODEL_AUDIT_OVERRIDE_KEYS,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    ModelResourceNames,
    ModelValidationRequest,
    NativeModelConfigInputs,
    NativeModelConfigSession,
)
from sqlbuild.compiler.compile.types import ModelInput
from sqlbuild.compiler.compiled_project.main._native_config_classes import native_config_classes
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSqlModelFile,
    ModelSchemaDeclaration,
    NamedSqlHookEntry,
    PythonHookEntry,
    SqlHookEntry,
)
from sqlbuild.compiler.model_config.main._native_config_error import native_config_error
from sqlbuild.compiler.path_defaults.main._select import select_path_default
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    MaterializationDefaultsConfig,
    ProjectConfig,
    SchemaModelEntry,
    TargetConfig,
)

_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_TABLE_BACKED_MATERIALIZATIONS: tuple[str, ...] = (
    MaterializationType.TABLE,
    MaterializationType.INCREMENTAL,
    MaterializationType.SNAPSHOT,
)
_PYTHON_VERSION: tuple[int, int] = (sys.version_info[0], sys.version_info[1])
type _BuiltNamespace = tuple[str | None, bool, str | None]
type _StorageOverrides = tuple[tuple[int | None, bool] | None, str | None]
type _BuiltConfig = tuple[
    dict[str, object],
    tuple[str, ...],
    _BuiltNamespace,
    _StorageOverrides,
    list[tuple[str, str]],
]
_MODEL_DESCRIPTION_KEY: str = "description"
_MODEL_SCHEMA_KEY: str = "model_schema"


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


def has_resolved_model_description(
    *,
    model_file: DiscoveredSqlModelFile,
    defaults: DefaultsConfig,
    path_defaults: dict[str, dict[str, object]],
    model_schemas: dict[str, ModelSchemaDeclaration],
) -> bool:
    """Return whether layered config or the model schema gives the model a description."""

    values: dict[str, object] = build_layered_model_values(
        defaults=defaults,
        path_defaults=path_defaults,
        matched_path_default=find_matching_path_default(
            model_file=model_file, path_defaults=path_defaults
        ),
        model_header_values=model_file.header_values,
    )
    schema_name: object | None = values.get(_MODEL_SCHEMA_KEY)
    schema: ModelSchemaDeclaration | None = (
        model_schemas.get(schema_name) if isinstance(schema_name, str) else None
    )
    return _is_non_empty_text(values.get(_MODEL_DESCRIPTION_KEY)) or _is_non_empty_text(
        schema.description if schema is not None else None
    )


def _is_non_empty_text(value: object | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


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


def legacy_schema_rows(
    schema_files: tuple[DiscoveredSchemaFile, ...],
) -> list[tuple[str, list[str]]]:
    """Each legacy schema file's relative path and the model names it declares."""

    rows: list[tuple[str, list[str]]] = []
    for schema_file in schema_files:
        rows.append(
            (str(schema_file.relative_path), [entry.name for entry in schema_file.model_entries])
        )
    return rows


def validate_declared_schema_models_are_attached(
    *,
    model_inputs: tuple[ModelInput, ...],
    schema_files: tuple[DiscoveredSchemaFile, ...],
) -> None:
    """Ensure every declared schema.yml model entry attaches within its directory scope."""

    attached_model_names: set[str | None] = {
        model_input.attached_schema_name for model_input in model_inputs
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


def native_model_config_session(
    *, inputs: NativeModelConfigInputs, names: ModelResourceNames
) -> NativeModelConfigSession:
    """Capture the project inputs every model's native config build and validation read."""

    project_config: ProjectConfig = inputs.project_config
    target: TargetConfig | None = inputs.target_config
    materialization_defaults: MaterializationDefaultsConfig = (
        project_config.materialization_defaults or MaterializationDefaultsConfig()
    )
    return NativeModelConfigSession(
        path_defaults=project_config.path_defaults,
        builder=_native.NativeModelConfigBuilder(
            (
                project_defaults_to_mapping(project_config.defaults),
                project_config.path_defaults,
                (SqlHookEntry, NamedSqlHookEntry, PythonHookEntry),
            ),
            (inputs.effective_vars, UnicodeEnvironment()),
            (
                (inputs.effective_target_name, inputs.run_id),
                None if target is None else (target.database, target.schema),
            ),
            (_PYTHON_VERSION, unicodedata.unidata_version),
        ),
        validator=_native.NativeModelValidator(
            (names.models, names.seeds, names.sources, names.functions, names.table_functions),
            set(names.custom_materializations),
            inputs.microbatch_concurrency,
            (_PYTHON_VERSION, unicodedata.unidata_version),
        ),
        inherited_storage={
            materialized: (
                resolve_time_travel_retention(
                    materialized=materialized,
                    model_value=None,
                    materialization_defaults=materialization_defaults,
                    target_config=target,
                    model_name="",
                ),
                resolve_table_type(
                    materialized=materialized,
                    model_value=None,
                    materialization_defaults=materialization_defaults,
                    target_config=target,
                    model_name="",
                ),
            )
            for materialized in (None, *_TABLE_BACKED_MATERIALIZATIONS)
        },
    )


def build_native_model_config(
    *,
    session: NativeModelConfigSession,
    model_file: DiscoveredSqlModelFile,
    matched_path_default: str | None,
) -> CompileModelConfig:
    """Build a model's effective config natively, raising its first config error."""

    built: object = session.builder.model_config(
        model_file.header_values,
        (matched_path_default, model_file.file_path.stem),
        native_config_classes(session=session, record_template_reads=record_template_reads),
    )
    if isinstance(built, _native.NativeConfigError):
        raise native_config_error(error=built)
    return cast(CompileModelConfig, built)


def native_model_validation(
    *, session: NativeModelConfigSession, request: ModelValidationRequest, rejected: list[bool]
) -> int | _native.NativeConfigError | None:
    """Validate natively: None, the first error, or the index of a rejected dbt reference."""

    config: CompileModelConfig = request.config
    return session.validator.validate(
        config.values,
        (
            request.model_file.file_path.stem,
            request.query_sql,
            str(request.model_file.relative_path),
        ),
        (
            [
                (str(reference.ref_kind), reference.ref_name, reference_rejected)
                for reference, reference_rejected in zip(request.references, rejected, strict=True)
            ],
            (
                None
                if request.declared_columns is None
                else [column.name for column in request.declared_columns]
            ),
            config.time_travel_retention.unmanaged,
            config.table_type.declared,
        ),
    )


def native_validation_error(
    *, error: _native.NativeConfigError, values: dict[str, object]
) -> Exception:
    """Return a native validator error, unmarked because validators read macro-expanded SQL."""

    return native_config_error(error=error, values=values)
