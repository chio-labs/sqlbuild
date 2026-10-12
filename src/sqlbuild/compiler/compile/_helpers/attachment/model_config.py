"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.config.retention import resolve_time_travel_retention
from sqlbuild.compiler.compile._helpers.config.table_type import resolve_table_type
from sqlbuild.compiler.compile._helpers.render.templating import (
    record_template_reads,
)
from sqlbuild.compiler.compile.classes.unicode_environment import UnicodeEnvironment
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    ModelValidationRequest,
    NativeModelConfigInputs,
    NativeModelConfigSession,
)
from sqlbuild.compiler.compile.types import ModelInput
from sqlbuild.compiler.compiled_project.main._native_config_classes import native_config_classes
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSqlModelFile,
    NamedSqlHookEntry,
    PythonHookEntry,
    SqlHookEntry,
)
from sqlbuild.compiler.model_config.main._native_config_error import native_config_error
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.spec.contracts.models import (
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


def native_model_config_session(
    *, inputs: NativeModelConfigInputs, validator: _native.NativeModelValidator
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
                project_config.defaults,
                project_config.path_defaults,
                (SqlHookEntry, NamedSqlHookEntry, PythonHookEntry),
            ),
            (inputs.effective_vars, UnicodeEnvironment()),
            (
                (inputs.effective_target_name, inputs.run_id),
                None if target is None else (target.database, target.schema),
            ),
        ),
        validator=validator,
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
