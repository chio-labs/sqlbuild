"""Published cursor-intrinsic compiler operation."""

from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    has_cursor_intrinsics,
    render_cursor_intrinsics,
)


def resolve_cursor_intrinsics(
    *, sql: str, start_sql: str | None = None, end_sql: str | None = None
) -> tuple[str, bool]:
    """Report intrinsic use and optionally render both bounds."""

    found: bool = has_cursor_intrinsics(sql)
    if not found or start_sql is None or end_sql is None:
        return sql, found
    return (
        render_cursor_intrinsics(sql=sql, start_sql=start_sql, end_sql=end_sql),
        True,
    )
