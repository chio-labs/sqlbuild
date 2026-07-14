"""SQL parenthesis matching entrypoint."""

from sqlbuild.compiler.sql_analysis._helpers.scanning import find_matching_paren_impl


def find_matching_paren(*, sql: str, open_paren_index: int, context: str = "SQL") -> int:
    """Find the closing parenthesis matching an opening parenthesis."""

    return find_matching_paren_impl(
        sql=sql,
        open_paren_index=open_paren_index,
        context=context,
    )
