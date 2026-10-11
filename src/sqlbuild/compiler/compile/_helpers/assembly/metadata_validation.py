"""Compile-owned inputs of the native semantic metadata checks."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.main._infer_native_query_columns import (
    infer_native_query_columns,
)
from sqlbuild.compiler.analysis_session.models import NativeColumnQuery, NativeQueryColumns
from sqlbuild.compiler.compile.models import CompiledModelSqlTestPayload
from sqlbuild.compiler.compile.types import CompiledProjectView


def sql_test_columns(
    *, project: CompiledProjectView, profile: ExpressionInferenceProfile
) -> dict[str, tuple[str, ...]]:
    """Infer fixture interfaces in one batch instead of repeating Python AST walks."""
    bodies: dict[str, None] = {}
    for test in project.sql_tests:
        if isinstance(test.payload, CompiledModelSqlTestPayload):
            for cte in (*test.payload.authored_ctes, *test.payload.expected_ctes):
                bodies[cte.sql_body] = None
    queries: tuple[str, ...] = tuple(bodies)
    if not queries:
        return {}
    analyses: tuple[NativeQueryColumns, ...] = infer_native_query_columns(
        queries=tuple(
            NativeColumnQuery(sql=sql, mode="batch", recover_cte_facts=False) for sql in queries
        ),
        profile=profile,
    )
    return {sql: _column_names(analysis) for sql, analysis in zip(queries, analyses, strict=True)}


def _column_names(analysis: NativeQueryColumns) -> tuple[str, ...]:
    return tuple(column.name for column in analysis.columns or ())


def names(value: object) -> tuple[str, ...]:
    """The column names a metadata config value lists."""

    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)):
        return tuple(item for item in value if isinstance(item, str))
    return ()
