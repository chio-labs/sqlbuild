"""Compile-time context and template resolution for model header values."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlbuild.compiler.compile._helpers.render.templating import expand_template_data
from sqlbuild.compiler.compile.constants import (
    COMPILE_INPUT_READS,
    MISSING_TEMPLATE_CONTEXT_MESSAGE_PART,
    MISSING_TEMPLATE_CONTEXT_VALUE_MESSAGE_PART,
    MISSING_TEMPLATE_VALUE_MESSAGE_PARTS,
    PRESERVE_TARGET_VALUE,
)
from sqlbuild.compiler.compile.types import CompileContextKey
from sqlbuild.compiler.model_config.constants import ENVIRONMENT_READ
from sqlbuild.compiler.model_config.main._expand_native_config_templates import (
    expand_native_config_templates,
)
from sqlbuild.compiler.model_config.main._native_config_error import native_config_error
from sqlbuild.compiler.model_config.models import (
    NativeTemplateExpansion,
    NativeTemplateRejection,
    TemplateResolutionFlags,
)
from sqlbuild.spec.contracts.models import TargetConfig


def resolve_early_model_templates(
    *,
    values: dict[str, object],
    effective_vars: dict[str, object],
    effective_target_name: str | None,
    run_id: str,
    native: bool = False,
) -> dict[str, object]:
    """Resolve `${name}`, `${ENV:...}`, and early `run.*` model templates."""

    return cast(
        dict[str, object],
        expand_config_templates(
            value=values,
            variables=effective_vars,
            context_values=build_run_context_values(
                effective_target_name=effective_target_name,
                run_id=run_id,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=True,
            native=native,
        ),
    )


def resolve_model_context_templates(
    *,
    values: dict[str, object],
    model_name: str,
    effective_target_name: str | None,
    run_id: str,
    native: bool = False,
) -> dict[str, object]:
    """Resolve model-bound `CTX` values once logical model identity is known."""

    return cast(
        dict[str, object],
        expand_config_templates(
            value=values,
            variables={},
            context_values=build_model_context_values(
                values=values,
                model_name=model_name,
                effective_target_name=effective_target_name,
                run_id=run_id,
                include_target_values=False,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=True,
            native=native,
        ),
    )


def resolve_chained_model_context_templates(
    *,
    values: dict[str, object],
    model_name: str,
    effective_target_name: str | None,
    run_id: str,
    native: bool = False,
) -> dict[str, object]:
    """Resolve twice so ${CTX:model.*} values may chain exactly one level without looping."""

    first_pass_values: dict[str, object] = resolve_model_context_templates(
        values=values,
        model_name=model_name,
        effective_target_name=effective_target_name,
        run_id=run_id,
        native=native,
    )
    return resolve_model_context_templates(
        values=first_pass_values,
        model_name=model_name,
        effective_target_name=effective_target_name,
        run_id=run_id,
        native=native,
    )


def resolve_target_context_templates(
    *,
    values: dict[str, object],
    model_name: str,
    effective_target_name: str | None,
    run_id: str,
    native: bool = False,
) -> dict[str, object]:
    """Resolve late `target.*` values after environment overrides finalize naming."""

    return cast(
        dict[str, object],
        expand_config_templates(
            value=values,
            variables={},
            context_values=build_model_context_values(
                values=values,
                model_name=model_name,
                effective_target_name=effective_target_name,
                run_id=run_id,
                include_target_values=True,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
            native=native,
        ),
    )


def build_model_context_values(
    *,
    values: dict[str, object],
    model_name: str,
    effective_target_name: str | None,
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
            effective_target_name=effective_target_name,
            run_id=run_id,
        ),
        CompileContextKey.MODEL_NAME: model_name,
        CompileContextKey.MODEL_DATABASE: logical_database,
        CompileContextKey.MODEL_SCHEMA: logical_schema,
        CompileContextKey.MODEL_ALIAS: logical_alias,
    }
    if not include_target_values:
        return context_values

    destination_database: str | None = logical_database
    destination_schema: str | None = logical_schema
    destination_table: str = logical_alias
    destination_qualified: str | None = None
    if destination_database is not None and destination_schema is not None:
        destination_qualified = f"{destination_database}.{destination_schema}.{destination_table}"
    elif destination_schema is not None:
        destination_qualified = f"{destination_schema}.{destination_table}"
    context_values[CompileContextKey.DESTINATION_DATABASE] = destination_database
    context_values[CompileContextKey.DESTINATION_SCHEMA] = destination_schema
    context_values[CompileContextKey.DESTINATION_TABLE] = destination_table
    context_values[CompileContextKey.DESTINATION_QUALIFIED] = destination_qualified
    return context_values


def build_run_context_values(
    *, effective_target_name: str | None, run_id: str
) -> dict[str, str | None]:
    """Build the compile-time CTX values known before resource-specific resolution."""

    return {
        CompileContextKey.RUN_ID: run_id,
        CompileContextKey.RUN_TARGET: effective_target_name,
    }


def apply_environment_database_schema_overrides(
    *,
    values: dict[str, object],
    effective_vars: dict[str, object],
    target_config: TargetConfig | None,
    model_context_values: dict[str, str | None],
    native: bool = False,
) -> dict[str, object]:
    """Return values with environment database/schema overrides applied."""

    if target_config is None:
        return dict(values)

    overridden: dict[str, object] = dict(values)
    if target_config.database is not None and target_config.database != PRESERVE_TARGET_VALUE:
        overridden["database"] = expand_config_templates(
            value=target_config.database,
            variables=effective_vars,
            context_values=model_context_values,
            context_label="environment database",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
            native=native,
        )
    if target_config.schema is not None and target_config.schema != PRESERVE_TARGET_VALUE:
        overridden["schema"] = expand_config_templates(
            value=target_config.schema,
            variables=effective_vars,
            context_values=model_context_values,
            context_label="environment schema",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
            native=native,
        )
    return overridden


def resolve_run_id(*, selected_run_id: str | None) -> str:
    """Resolve a stable compile invocation id."""

    if selected_run_id is not None:
        return selected_run_id
    timestamp_prefix: str = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    unique_suffix: str = uuid4().hex[:12]
    return f"{timestamp_prefix}_{unique_suffix}"


def expand_config_templates(
    *,
    value: object,
    variables: dict[str, object],
    context_values: dict[str, str | None],
    context_label: str,
    allow_context: bool,
    preserve_context_tokens: bool,
    preserve_unknown_context: bool,
    native: bool,
) -> object:
    """Expand like `expand_template_data`, natively when set; unsupported values run Python."""

    outcome: NativeTemplateExpansion | NativeTemplateRejection | str | None = (
        expand_native_config_templates(
            value=value,
            variables=variables,
            context_values=context_values,
            flags=TemplateResolutionFlags(
                allow_context=allow_context,
                preserve_context_tokens=preserve_context_tokens,
                preserve_unknown_context=preserve_unknown_context,
            ),
            context_label=context_label,
        )
        if native
        else None
    )
    if isinstance(outcome, NativeTemplateExpansion):
        record_template_reads(outcome.reads)
        return outcome.value
    if isinstance(outcome, NativeTemplateRejection) and not _names_missing_template_value(
        context_label
    ):
        record_template_reads(outcome.reads)
        raise native_config_error(error=outcome.error)
    return expand_template_data(
        value=value,
        variables=variables,
        context_values=context_values,
        context_label=context_label,
        allow_context=allow_context,
        preserve_context_tokens=preserve_context_tokens,
        preserve_unknown_context=preserve_unknown_context,
    )


def _names_missing_template_value(context_label: str) -> bool:
    """Whether Python's `coalesce` would read errors naming this label as missing values."""

    return any(
        part in context_label
        for part in (
            *MISSING_TEMPLATE_VALUE_MESSAGE_PARTS,
            MISSING_TEMPLATE_CONTEXT_MESSAGE_PART,
            MISSING_TEMPLATE_CONTEXT_VALUE_MESSAGE_PART,
        )
    )


def record_template_reads(reads: tuple[tuple[str, str], ...]) -> None:
    """Record native template environment and context reads for project reuse, in order."""

    for kind, name in reads:
        if kind == ENVIRONMENT_READ:
            COMPILE_INPUT_READS.environment_read(name)
        else:
            COMPILE_INPUT_READS.context_read(name)
