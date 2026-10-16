"""Public adapter safe-cast nullability inference operation."""

from sqlbuild._native import InferredNullability, infer_safe_cast_nullability


def safe_cast_nullability(args: tuple[InferredNullability, ...]) -> InferredNullability:
    """Infer safe-cast nullability without assuming conversion succeeds."""

    return infer_safe_cast_nullability(args)
