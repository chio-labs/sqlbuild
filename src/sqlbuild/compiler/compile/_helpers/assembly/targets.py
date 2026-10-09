"""Compiled model and seed relation target resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.config.namespace_validation import (
    validate_preserved_logical_namespace,
)
from sqlbuild.compiler.compile._helpers.render.templating import expand_template_data
from sqlbuild.compiler.compile.constants import PRESERVE_TARGET_VALUE
from sqlbuild.compiler.compile.models import CompiledRelationLocation, CompileModelInput
from sqlbuild.spec.contracts.models import DefaultsConfig, SchemaSeedEntry, TargetConfig


def build_model_relation_target(
    *, model_input: CompileModelInput, model_name: str
) -> CompiledRelationLocation:
    """Resolve one model's configured physical and logical destination."""

    raw_database: object | None = model_input.config.values.get("database")
    raw_schema: object | None = model_input.config.values.get("schema")
    raw_alias: object | None = model_input.config.values.get("alias")
    database: str | None = raw_database if isinstance(raw_database, str) else None
    schema: str | None = raw_schema if isinstance(raw_schema, str) else None
    name: str = raw_alias if isinstance(raw_alias, str) else model_name
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=name,
        qualified_name=None,
        logical_schema=model_input.config.logical_schema,
        logical_database=model_input.config.logical_database,
    )


def build_seed_relation_target(
    *,
    seed_entry: SchemaSeedEntry,
    defaults: DefaultsConfig,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> CompiledRelationLocation:
    """Resolve one seed's target-aware physical and logical destination."""

    logical_namespace: tuple[str | None, str | None] = _resolve_seed_logical_namespace(
        defaults=defaults,
        effective_vars=effective_vars,
    )
    logical_database: str | None = logical_namespace[0]
    logical_schema: str | None = logical_namespace[1]
    if seed_entry.database is not None:
        logical_database = _expand_seed_target_value(
            raw_value=seed_entry.database,
            seed_name=seed_entry.name,
            database=logical_database,
            schema=logical_schema,
            effective_vars=effective_vars,
            context_label=f"seed '{seed_entry.name}' database",
        )
    if seed_entry.schema is not None:
        logical_schema = _expand_seed_target_value(
            raw_value=seed_entry.schema,
            seed_name=seed_entry.name,
            database=logical_database,
            schema=logical_schema,
            effective_vars=effective_vars,
            context_label=f"seed '{seed_entry.name}' schema",
        )
    validate_preserved_logical_namespace(
        resource_label=f"Seed '{seed_entry.name}'",
        logical_database=logical_database,
        logical_schema=logical_schema,
        target_config=target_config,
    )
    database, schema = _apply_seed_target_overrides(
        logical_database=logical_database,
        logical_schema=logical_schema,
        target_config=target_config,
        effective_vars=effective_vars,
    )
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=seed_entry.name,
        qualified_name=None,
        logical_database=logical_database,
        logical_schema=logical_schema,
    )


def _resolve_seed_logical_namespace(
    *,
    defaults: DefaultsConfig,
    effective_vars: dict[str, object],
) -> tuple[str | None, str | None]:
    database: str | None = _expand_seed_default_value(
        raw_value=(
            defaults.seed_database if defaults.seed_database is not None else defaults.database
        ),
        effective_vars=effective_vars,
        context_label="default seed database",
    )
    schema: str | None = _expand_seed_default_value(
        raw_value=defaults.seed_schema if defaults.seed_schema is not None else defaults.schema,
        effective_vars=effective_vars,
        context_label="default seed schema",
    )
    return database, schema


def _apply_seed_target_overrides(
    *,
    logical_database: str | None,
    logical_schema: str | None,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> tuple[str | None, str | None]:
    if target_config is None:
        return logical_database, logical_schema
    database: str | None = logical_database
    schema: str | None = logical_schema
    if target_config.database is not None and target_config.database != PRESERVE_TARGET_VALUE:
        database = _expand_seed_environment_value(
            raw_value=target_config.database,
            effective_vars=effective_vars,
            context_label="target database",
        )
    if target_config.schema is not None and target_config.schema != PRESERVE_TARGET_VALUE:
        schema = _expand_seed_environment_value(
            raw_value=target_config.schema,
            effective_vars=effective_vars,
            context_label="target schema",
        )
    return database, schema


def _expand_seed_default_value(
    *, raw_value: str | None, effective_vars: dict[str, object], context_label: str
) -> str | None:
    if raw_value is None:
        return None
    return _expand_seed_environment_value(
        raw_value=raw_value,
        effective_vars=effective_vars,
        context_label=context_label,
    )


def _expand_seed_environment_value(
    *, raw_value: str, effective_vars: dict[str, object], context_label: str
) -> str | None:
    if raw_value == PRESERVE_TARGET_VALUE:
        return None
    return str(
        expand_template_data(
            value=raw_value,
            variables=effective_vars,
            context_values={},
            context_label=context_label,
            allow_context=False,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    )


def _expand_seed_target_value(
    *,
    raw_value: str,
    seed_name: str,
    database: str | None,
    schema: str | None,
    effective_vars: dict[str, object],
    context_label: str,
) -> str | None:
    if raw_value == PRESERVE_TARGET_VALUE:
        return None
    return str(
        expand_template_data(
            value=raw_value,
            variables=effective_vars,
            context_values={
                "model.name": seed_name,
                "model.database": database,
                "model.schema": schema,
                "model.alias": seed_name,
                "destination.database": database,
                "destination.schema": schema,
                "destination.table": seed_name,
                "destination.qualified": _build_seed_destination_qualified_context(
                    database=database,
                    schema=schema,
                    name=seed_name,
                ),
            },
            context_label=context_label,
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    )


def _build_seed_destination_qualified_context(
    *, database: str | None, schema: str | None, name: str
) -> str | None:
    if database is not None and schema is not None:
        return f"{database}.{schema}.{name}"
    if schema is not None:
        return f"{schema}.{name}"
    return None
