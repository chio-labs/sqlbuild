"""SQL block comment scanning entrypoint."""

from sqlbuild.compiler.sql_analysis._helpers.scanning import skip_block_comment_impl


def skip_block_comment(*, sql: str, start: int, context: str = "SQL") -> int:
    """Skip past an SQL block comment."""

    return skip_block_comment_impl(sql=sql, start=start, context=context)
