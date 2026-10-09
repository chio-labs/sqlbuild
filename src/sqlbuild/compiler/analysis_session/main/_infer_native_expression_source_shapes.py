"""Infer expression-source shapes natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session._helpers.expression_shapes import (
    native_expression_source_shapes,
)


def infer_native_expression_source_shapes(
    *, expressions: tuple[str, ...], profile: ExpressionInferenceProfile
) -> tuple[dict[str, str] | None, ...] | None:
    """Return one shape per expression, or None where Python must infer the shapes."""

    return native_expression_source_shapes(expressions=expressions, profile=profile)
