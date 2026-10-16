"""Public adapter conditional nullability inference operation."""

from sqlbuild._native import InferredNullability, infer_conditional_result_nullability


def conditional_result_nullability(
    args: tuple[InferredNullability, ...],
) -> InferredNullability:
    """Infer IF/IFF-style nullability from true and false result arguments."""

    return infer_conditional_result_nullability(args)
