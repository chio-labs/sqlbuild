"""Infer the output columns of queries outside the native analysis session."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session._helpers.query_columns import native_query_columns
from sqlbuild.compiler.analysis_session.models import NativeColumnQuery, NativeQueryColumns
from sqlbuild.compiler.lineage.types import InferredNullability


def infer_native_query_columns(
    *,
    queries: Sequence[NativeColumnQuery],
    profile: ExpressionInferenceProfile,
    column_types_by_table: Mapping[str, Mapping[str, str]] | None = None,
    column_nullability_by_table: Mapping[str, Mapping[str, InferredNullability]] | None = None,
) -> tuple[NativeQueryColumns, ...]:
    """Each query's columns; a native internal failure raises `NativeCompilerError`."""

    return native_query_columns(
        queries=queries,
        profile=profile,
        column_types_by_table=column_types_by_table or {},
        column_nullability_by_table=column_nullability_by_table or {},
    )
