"""SQL line comment scanning entrypoint."""

from sqlbuild.compiler.sql_analysis.helpers.scanning import skip_line_comment_impl


def skip_line_comment(*, sql: str, start: int) -> int:
    """Skip past an SQL line comment."""

    return skip_line_comment_impl(sql=sql, start=start)
