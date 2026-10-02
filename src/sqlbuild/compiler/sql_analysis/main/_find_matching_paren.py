"""SQL parenthesis matching entrypoint."""

from sqlbuild.compiler.sql_analysis._helpers.scanning import find_matching_paren_impl
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def find_matching_paren(
    *,
    sql: str,
    open_paren_index: int,
    context: str = "SQL",
    syntax: SqlLexicalSyntax | None = None,
) -> int:
    """Find the closing parenthesis, ending quoted text and comments per the optional dialect."""

    return find_matching_paren_impl(
        sql=sql,
        open_paren_index=open_paren_index,
        context=context,
        syntax=syntax,
    )
