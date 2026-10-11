"""Infer query output column rows natively outside the analysis session."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session._helpers.query_columns import native_query_column_rows
from sqlbuild.compiler.analysis_session.models import NativeColumnQuery
from sqlbuild.compiler.analysis_session.types import ColumnRow
from sqlbuild.compiler.lineage.types import InferredNullability


def infer_native_query_column_rows(
    *,
    queries: Sequence[NativeColumnQuery],
    profile: ExpressionInferenceProfile,
    column_nullability_by_table: Mapping[str, Mapping[str, InferredNullability]] | None = None,
) -> list[tuple[bool, list[ColumnRow] | None, bool]]:
    """Each query's `(succeeded, column rows, has star)`; a native internal failure raises."""

    return native_query_column_rows(
        queries=queries,
        profile=profile,
        column_types_by_table={},
        column_nullability_by_table=column_nullability_by_table or {},
    )
