"""Fixture-column inference implementation."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.main._infer_native_query_columns import (
    infer_native_query_columns,
)
from sqlbuild.compiler.analysis_session.models import NativeColumnQuery, NativeQueryColumns
from sqlbuild.compiler.compile.models import (
    FixtureColumnInference,
    InferredColumn,
)


def infer_fixture_column_facts(
    *, query_sql: str, inference_profile: ExpressionInferenceProfile
) -> FixtureColumnInference | None:
    """Infer fixture columns and identify explicitly untyped NULL projections."""

    analysis: NativeQueryColumns = infer_native_query_columns(
        queries=(NativeColumnQuery(sql=query_sql, mode="legacy", recover_cte_facts=False),),
        profile=inference_profile,
    )[0]
    if not analysis.succeeded or analysis.has_star or analysis.columns is None:
        return None
    simple_types, null_literal_names, quoted_names = _simple_projection_facts(
        query_sql=query_sql,
        dialect=inference_profile.sql_analysis_dialect,
    )
    return FixtureColumnInference(
        columns=tuple(
            InferredColumn(
                name=column.name,
                type=column.type or simple_types.get(column.name.casefold()),
                nullability=column.nullability,
            )
            for column in analysis.columns
        ),
        null_literal_names=null_literal_names,
        quoted_names=quoted_names,
    )


def _simple_projection_facts(
    *, query_sql: str, dialect: str | None
) -> tuple[dict[str, str], frozenset[str], frozenset[str]]:
    types: list[tuple[str, str]]
    null_literal_names: list[str]
    quoted_names: list[str]
    types, null_literal_names, quoted_names = _native.fixture_projection_facts(query_sql, dialect)
    return dict(types), frozenset(null_literal_names), frozenset(quoted_names)
