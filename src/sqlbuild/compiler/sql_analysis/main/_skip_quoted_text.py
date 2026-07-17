"""Quoted SQL text scanning entrypoint."""

from sqlbuild.compiler.sql_analysis._helpers.scanning import skip_quoted_text_impl


def skip_quoted_text(*, sql: str, start: int, context: str = "SQL") -> int:
    """Skip past a quoted string starting at the supplied position."""

    return skip_quoted_text_impl(sql=sql, start=start, context=context)
