"""Expand one authored SQL body while reporting each substitution's span."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.render.sql_vars import expand_authored_sql_with_spans
from sqlbuild.compiler.compile.models import (
    ConstantDeclaration,
    DeclarationResolutionContext,
    EnumDeclaration,
    ExpansionSpan,
    SqlExpansionContext,
)


def expand_sql_with_spans(
    *, sql: str, file_path: Path, context: SqlExpansionContext
) -> tuple[str, tuple[tuple[ExpansionSpan, ...], ...]]:
    """Expand authored SQL and return each expansion pass's substitution spans."""

    local_declarations: DeclarationResolutionContext | None = context.local_declarations.get(
        file_path
    )
    enums: dict[str, EnumDeclaration] = context.enums
    constants: dict[str, ConstantDeclaration] = context.constants
    if local_declarations is not None:
        enums = enums | local_declarations.enums
        constants = constants | local_declarations.constants
    return expand_authored_sql_with_spans(
        sql=sql,
        file_path=file_path,
        effective_vars=context.effective_vars,
        loaded_macros=context.loaded_macros,
        macro_context=context.macro_context,
        enums=enums,
        constants=constants,
    )
