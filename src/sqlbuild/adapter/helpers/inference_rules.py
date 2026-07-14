"""Public expression inference capability for adapters."""

from __future__ import annotations

from sqlbuild.compiler.lineage.types import InferredNullability


def first_arg_nullability(
    args: tuple[InferredNullability, ...],
) -> InferredNullability:
    """Return the first argument's nullability for null-propagating unary functions."""

    if not args:
        return InferredNullability.UNKNOWN
    return args[0]


def conditional_result_nullability(
    args: tuple[InferredNullability, ...],
) -> InferredNullability:
    """Infer IF/IFF-style nullability from true/false result arguments."""

    source_target_and_default_argument_count: int = 3
    if len(args) < source_target_and_default_argument_count:
        return InferredNullability.UNKNOWN
    result_args: tuple[InferredNullability, InferredNullability] = (args[1], args[2])
    if all(value == InferredNullability.NON_NULL for value in result_args):
        return InferredNullability.NON_NULL
    if any(value == InferredNullability.NULLABLE for value in result_args):
        return InferredNullability.NULLABLE
    return InferredNullability.UNKNOWN


def safe_cast_nullability(
    args: tuple[InferredNullability, ...],
) -> InferredNullability:
    """Infer SAFE_CAST/TRY_CAST nullability without assuming conversion succeeds."""

    if args and args[0] == InferredNullability.NULLABLE:
        return InferredNullability.NULLABLE
    return InferredNullability.UNKNOWN
