"""Public fixture-column inference entrypoint."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.fixture_columns import (
    infer_fixture_column_facts as _infer_fixture_column_facts,
)
from sqlbuild.compiler.compile.models import FixtureColumnInference


def infer_fixture_column_facts(
    *, query_sql: str, inference_profile: ExpressionInferenceProfile
) -> FixtureColumnInference | None:
    """Infer fixture columns and identify explicitly untyped NULL projections."""

    return _infer_fixture_column_facts(
        query_sql=query_sql,
        inference_profile=inference_profile,
    )
