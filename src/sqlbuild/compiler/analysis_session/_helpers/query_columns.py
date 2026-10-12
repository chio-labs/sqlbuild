"""Python's per-query column analysis outside the session, run natively."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import FunctionNullabilityRule
from sqlbuild.compiler.analysis_session._helpers.profile_rows import (
    adapter_nullability_rules,
    nullability_rule_rows,
    shape_rows,
)
from sqlbuild.compiler.analysis_session.models import NativeColumnQuery, NativeQueryColumns
from sqlbuild.compiler.analysis_session.types import ColumnRow
from sqlbuild.compiler.compile.models import CompileSqlReference, InferredColumn
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import (
    NATIVE_DIALECT_ALIASES,
    TABLE_FUNCTION_ANALYSIS_PREFIX,
)
from sqlbuild.compiler.sql_analysis.main._binding_catalog import create_binding_catalog

_BATCH_MODE: str = "batch"
_LINEAGE_RESOURCE_TYPES: dict[str, CompiledResourceType] = {
    SqlReferenceKind.REF: CompiledResourceType.MODEL,
    SqlReferenceKind.SOURCE: CompiledResourceType.SOURCE,
    SqlReferenceKind.SEED: CompiledResourceType.SEED,
    SqlReferenceKind.TABLE_FUNCTION: CompiledResourceType.TABLE_FN,
}


def native_query_columns(
    *,
    queries: Sequence[NativeColumnQuery],
    profile: ExpressionInferenceProfile,
    column_types_by_table: Mapping[str, Mapping[str, str]],
    column_nullability_by_table: Mapping[str, Mapping[str, InferredNullability]],
) -> tuple[NativeQueryColumns, ...]:
    """Each query's columns; a native internal failure raises `NativeCompilerError`."""

    return tuple(
        NativeQueryColumns(
            succeeded=succeeded,
            columns=None if columns is None else _inferred_columns(columns),
            has_star=has_star,
        )
        for succeeded, columns, has_star in native_query_column_rows(
            queries=queries,
            profile=profile,
            column_types_by_table=column_types_by_table,
            column_nullability_by_table=column_nullability_by_table,
        )
    )


def native_query_column_rows(
    *,
    queries: Sequence[NativeColumnQuery],
    profile: ExpressionInferenceProfile,
    column_types_by_table: Mapping[str, Mapping[str, str]],
    column_nullability_by_table: Mapping[str, Mapping[str, InferredNullability]],
) -> list[tuple[bool, list[ColumnRow] | None, bool]]:
    """Each query's `(succeeded, column rows, has star)` as the native analysis returns it."""

    if not queries:
        return []
    dialect: str = profile.sql_analysis_dialect or "generic"
    dialect = NATIVE_DIALECT_ALIASES.get(dialect, dialect)
    catalog: Any | None = (
        (
            profile.binding_catalog
            or create_binding_catalog(
                dialect=dialect,
                quoted_ignore_case=profile.quoted_identifiers_ignore_case,
                known_functions=(),
                known_types=(),
                relations={},
            )
        )
        if any(query.mode == _BATCH_MODE for query in queries)
        else None
    )
    adapter_rules: dict[str, FunctionNullabilityRule] = adapter_nullability_rules(profile)
    return _native.infer_query_columns(
        None if catalog is None else catalog.native,
        (
            dialect,
            list(profile.function_return_types.items()),
            nullability_rule_rows(profile),
            shape_rows(column_types_by_table),
            shape_rows(column_nullability_by_table),
            [_query_row(query) for query in queries],
            profile.sql_analysis_dialect or "generic",
        ),
        (adapter_rules, InferredNullability) if adapter_rules else None,
    )


def _inferred_columns(
    columns: list[tuple[str, str | None, str]],
) -> tuple[InferredColumn, ...]:
    return tuple(
        InferredColumn(name=name, type=data_type, nullability=InferredNullability(nullability))
        for name, data_type, nullability in columns
    )


def _query_row(query: NativeColumnQuery) -> tuple[object, ...]:
    references: tuple[CompileSqlReference, ...] = query.references
    return (
        query.sql,
        list((query.placeholders or {}).items()),
        [_analysis_name(reference) for reference in references],
        [
            (name, resource_type, resource_name)
            for name, (resource_type, resource_name) in _lineage_references(references).items()
        ],
        query.recover_cte_facts,
        query.mode,
    )


def _lineage_references(
    references: tuple[CompileSqlReference, ...],
) -> dict[str, tuple[str, str]]:
    """Each lineage reference's analysis name, resource type and name; the last wins in place."""

    return {
        _analysis_name(reference): (
            _LINEAGE_RESOURCE_TYPES[reference.ref_kind].value,
            reference.ref_name,
        )
        for reference in references
        if reference.ref_kind in _LINEAGE_RESOURCE_TYPES
    }


def _analysis_name(reference: CompileSqlReference) -> str:
    if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION:
        return f"{TABLE_FUNCTION_ANALYSIS_PREFIX}{reference.ref_name}"
    return reference.ref_name
