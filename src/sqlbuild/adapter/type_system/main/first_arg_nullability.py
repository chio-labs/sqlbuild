"""Public adapter unary nullability inference operation."""

from sqlbuild._native import InferredNullability, infer_first_arg_nullability


def first_arg_nullability(args: tuple[InferredNullability, ...]) -> InferredNullability:
    """Return the first argument's nullability for null-propagating unary functions."""

    return infer_first_arg_nullability(args)
