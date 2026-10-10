"""Python's per-query column analysis outside the session, run natively."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import FunctionNullabilityRule
from sqlbuild.compiler.analysis_session._helpers.deferral_records import record_analysis_deferral
from sqlbuild.compiler.analysis_session._helpers.profile_rows import (
    adapter_nullability_rules,
    nullability_rule_rows,
    shape_rows,
)
from sqlbuild.compiler.analysis_session.constants import ADAPTER_NULLABILITY_CALLBACK
from sqlbuild.compiler.analysis_session.models import NativeColumnQuery, NativeQueryColumns
from sqlbuild.compiler.compile._helpers.sharing.binding import lineage_reference_map
from sqlbuild.compiler.compile.models import CompileSqlReference, InferredColumn
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import (
    NATIVE_DIALECT_ALIASES,
    TABLE_FUNCTION_ANALYSIS_PREFIX,
)
from sqlbuild.compiler.sql_analysis.main._binding_catalog import create_binding_catalog
from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql

_BATCH_MODE: str = "batch"
_NORMALIZED_MODES: frozenset[str] = frozenset({"parse", "legacy"})


def native_query_columns(
    *,
    queries: Sequence[NativeColumnQuery],
    profile: ExpressionInferenceProfile,
    column_types_by_table: Mapping[str, Mapping[str, str]],
    column_nullability_by_table: Mapping[str, Mapping[str, InferredNullability]],
) -> tuple[NativeQueryColumns, ...]:
    """Each query's columns; a native internal failure raises `NativeCompilerError`."""

    if not queries:
        return ()
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
    if adapter_rules:
        record_analysis_deferral(kind=ADAPTER_NULLABILITY_CALLBACK)
    rows: list[tuple[bool, list[tuple[str, str | None, str]] | None, bool]] = (
        _native.infer_query_columns(
            None if catalog is None else catalog.native,
            (
                dialect,
                list(profile.function_return_types.items()),
                nullability_rule_rows(profile),
                shape_rows(column_types_by_table),
                shape_rows(column_nullability_by_table),
                [
                    _query_row(query=query, dialect=profile.sql_analysis_dialect)
                    for query in queries
                ],
            ),
            (adapter_rules, InferredNullability) if adapter_rules else None,
        )
    )
    return tuple(
        NativeQueryColumns(
            succeeded=succeeded,
            columns=(
                None
                if columns is None
                else tuple(
                    InferredColumn(
                        name=name, type=data_type, nullability=InferredNullability(nullability)
                    )
                    for name, data_type, nullability in columns
                )
            ),
            has_star=has_star,
        )
        for succeeded, columns, has_star in rows
    )


def _query_row(*, query: NativeColumnQuery, dialect: str | None) -> tuple[object, ...]:
    references: tuple[CompileSqlReference, ...] = query.references
    return (
        normalize_analysis_sql(sql=query.sql, dialect=dialect)
        if query.mode in _NORMALIZED_MODES
        else query.sql,
        list((query.placeholders or {}).items()),
        [_analysis_name(reference) for reference in references],
        [
            (name, resource_type.value, resource_name)
            for name, (resource_type, resource_name) in lineage_reference_map(references).items()
        ],
        query.recover_cte_facts,
        query.mode,
    )


def _analysis_name(reference: CompileSqlReference) -> str:
    if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION:
        return f"{TABLE_FUNCTION_ANALYSIS_PREFIX}{reference.ref_name}"
    return reference.ref_name
