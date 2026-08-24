"""Public standard microbatch-state index DDL rendering entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.microbatches.constants import (
    MICROBATCH_STANDARD_INDEXES,
    MICROBATCH_TABLE_NAME,
)


def build_create_index_sqls(
    *,
    database: str | None,
    schema: str,
    render_identifier: Callable[[str], str],
    render_qualified_name: Callable[..., str | None],
) -> tuple[str, ...]:
    """Build non-unique scope and provenance indexes for indexed warehouses."""

    table: str = (
        render_qualified_name(database=database, schema=schema, name=MICROBATCH_TABLE_NAME)
        or f"{schema}.{MICROBATCH_TABLE_NAME}"
    )
    statements: list[str] = []
    for index_name, columns in MICROBATCH_STANDARD_INDEXES.items():
        rendered_columns: tuple[str, ...] = tuple(render_identifier(column) for column in columns)
        statements.append(
            f"CREATE INDEX IF NOT EXISTS {render_identifier(index_name)} ON {table} "
            f"({', '.join(rendered_columns)})"
        )
    return tuple(statements)
