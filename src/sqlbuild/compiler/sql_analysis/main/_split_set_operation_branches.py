"""Top-level SQL set-operation branch splitting entrypoint."""

from sqlbuild.compiler.sql_analysis._helpers.set_operations import (
    split_set_operation_branches_impl,
)


def split_set_operation_branches(*, sql: str, context: str = "SQL") -> tuple[str, ...]:
    """Split SQL on top-level `UNION`, `INTERSECT` and `EXCEPT`, ignoring quotes and comments."""

    return split_set_operation_branches_impl(sql=sql, context=context)
