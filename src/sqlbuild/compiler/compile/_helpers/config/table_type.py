"""Snowflake table-type policy resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.config.retention import resolve_time_travel_retention
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import ResolvedTableType
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.spec.contracts.models import (
    MaterializationDefaultsConfig,
    ResolvedTimeTravelRetention,
    TargetConfig,
)
from sqlbuild.spec.contracts.types import TableType, TableTypeSource, TableTypeValue

_STORAGE_POLICY_KEYS: frozenset[str] = frozenset({"time_travel_retention", "table_type"})


def resolve_storage_policies(
    *,
    resolved_values: dict[str, object],
    model_header_values: dict[str, object],
    materialization_defaults: MaterializationDefaultsConfig | None,
    target_config: TargetConfig | None,
    model_name: str,
) -> tuple[dict[str, object], ResolvedTimeTravelRetention, ResolvedTableType]:
    """Resolve storage policies and remove authored values from ordinary model config."""

    defaults: MaterializationDefaultsConfig = (
        materialization_defaults or MaterializationDefaultsConfig()
    )
    retention: ResolvedTimeTravelRetention = resolve_time_travel_retention(
        materialized=resolved_values.get("materialized"),
        model_value=model_header_values.get("time_travel_retention"),
        materialization_defaults=defaults,
        target_config=target_config,
        model_name=model_name,
    )
    table_type: ResolvedTableType = resolve_table_type(
        materialized=resolved_values.get("materialized"),
        model_value=model_header_values.get("table_type"),
        materialization_defaults=defaults,
        target_config=target_config,
        model_name=model_name,
    )
    cleaned_values: dict[str, object] = {
        key: value for key, value in resolved_values.items() if key not in _STORAGE_POLICY_KEYS
    }
    return cleaned_values, retention, table_type


def resolve_table_type(
    *,
    materialized: object | None,
    model_value: object | None,
    materialization_defaults: MaterializationDefaultsConfig,
    target_config: TargetConfig | None,
    model_name: str,
) -> ResolvedTableType:
    """Resolve target, materialization, and model table-type precedence."""

    value: TableType = TableType.TRANSIENT
    source: TableTypeSource = TableTypeSource.DEFAULT
    declared: bool = False
    materialization: str | None = materialized if isinstance(materialized, str) else None
    supported: bool = MaterializationType.is_table_backed(materialized=materialization)
    if supported and target_config is not None and target_config.default_table_type is not None:
        value = target_config.default_table_type
        source = TableTypeSource.TARGET
        declared = True
    if supported and materialization is not None:
        materialization_value: TableType | None = getattr(
            materialization_defaults, materialization
        ).table_type
        if materialization_value is not None:
            value = materialization_value
            source = TableTypeSource.MATERIALIZATION
            declared = True
    if model_value is not None:
        if not isinstance(model_value, str):
            raise CompileInputError(
                f"model '{model_name}': table_type must be permanent, transient, or inherit"
            )
        if model_value != TableTypeValue.INHERIT:
            try:
                value = TableType(model_value)
            except ValueError as exc:
                raise CompileInputError(
                    f"model '{model_name}': table_type must be permanent, transient, or inherit"
                ) from exc
            source = TableTypeSource.MODEL
            declared = True
    return ResolvedTableType(value=value, source=source, declared=declared)
