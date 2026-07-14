"""Public adapter conditional nullability inference operation."""

from sqlbuild.adapter._helpers.inference_rules import (
    conditional_result_nullability as _conditional_result_nullability,
)
from sqlbuild.compiler.lineage.types import InferredNullability


def conditional_result_nullability(
    args: tuple[InferredNullability, ...],
) -> InferredNullability:
    """Infer IF/IFF-style nullability from true and false result arguments."""

    return _conditional_result_nullability(args)
