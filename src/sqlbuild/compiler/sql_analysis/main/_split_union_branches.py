"""Top-level SQL UNION branch splitting entrypoint."""

from sqlbuild.compiler.sql_analysis._helpers.set_operations import split_union_branches_impl


def split_union_branches(*, sql: str, context: str = "SQL") -> tuple[str, ...]:
    """Split SQL on top-level `UNION [ALL | DISTINCT]`, ignoring quotes and comments."""

    return split_union_branches_impl(sql=sql, context=context)
