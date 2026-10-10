"""Snowflake table-type policy resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import ResolvedTableType
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.spec.contracts.models import (
    MaterializationDefaultsConfig,
    TargetConfig,
)
from sqlbuild.spec.contracts.types import TableType, TableTypeSource, TableTypeValue


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
