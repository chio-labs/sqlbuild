"""Expand one authored SQL body while reporting each substitution's span."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.render.sql_vars import expand_authored_sql_with_spans
from sqlbuild.compiler.compile.models import ExpansionSpan, SqlExpansionContext


def expand_sql_with_spans(
    *, sql: str, file_path: Path, context: SqlExpansionContext
) -> tuple[str, tuple[tuple[ExpansionSpan, ...], ...]]:
    """Expand authored SQL and return each expansion pass's substitution spans."""

    return expand_authored_sql_with_spans(
        sql=sql,
        file_path=file_path,
        effective_vars=context.effective_vars,
        loaded_macros=context.loaded_macros,
        macro_context=context.macro_context,
        enums=context.enums,
        constants=context.constants,
    )
