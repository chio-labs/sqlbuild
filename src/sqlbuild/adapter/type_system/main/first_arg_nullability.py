"""Public adapter unary nullability inference operation."""

from sqlbuild._native import infer_first_arg_nullability
from sqlbuild.compiler.lineage.types import InferredNullability


def first_arg_nullability(args: tuple[InferredNullability, ...]) -> InferredNullability:
    """Return the first argument's nullability for null-propagating unary functions."""

    return infer_first_arg_nullability(args)
