"""Public adapter safe-cast nullability inference operation."""

from sqlbuild.adapter.helpers.inference_rules import (
    safe_cast_nullability as _safe_cast_nullability,
)
from sqlbuild.compiler.lineage.types import InferredNullability


def safe_cast_nullability(args: tuple[InferredNullability, ...]) -> InferredNullability:
    """Infer safe-cast nullability without assuming conversion succeeds."""

    return _safe_cast_nullability(args)
