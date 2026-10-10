"""Infer expression-source shapes natively."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session._helpers.expression_shapes import (
    native_expression_source_shapes,
)


def infer_native_expression_source_shapes(
    *, expressions: tuple[str, ...], profile: ExpressionInferenceProfile
) -> tuple[dict[str, str] | None, ...]:
    """One shape per expression; a native internal failure raises `NativeCompilerError`."""

    return native_expression_source_shapes(expressions=expressions, profile=profile)
