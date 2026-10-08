"""Infer expression-source shapes natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile


def infer_native_expression_source_shapes(
    *, expressions: tuple[str, ...], profile: ExpressionInferenceProfile
) -> tuple[dict[str, str] | None, ...] | None:
    """Return one shape per expression, or None where Python must infer the shapes."""

    return None
