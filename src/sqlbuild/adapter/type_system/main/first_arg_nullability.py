"""Public adapter unary nullability inference operation."""

from sqlbuild.adapter.type_system._helpers.inference_rules import (
    first_arg_nullability as _first_arg_nullability,
)
from sqlbuild.compiler.lineage.types import InferredNullability


def first_arg_nullability(args: tuple[InferredNullability, ...]) -> InferredNullability:
    """Return the first argument's nullability for null-propagating unary functions."""

    return _first_arg_nullability(args)
