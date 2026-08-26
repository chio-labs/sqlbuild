"""Expand one authored SQL body while reporting each substitution's span."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.render.declarations import resolve_declaration_context
from sqlbuild.compiler.compile._helpers.render.sql_vars import expand_authored_sql_with_spans
from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
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
    declarations: DeclarationResolutionContext = DeclarationResolutionContext(
        enums=context.enums,
        constants=context.constants,
    )
    if context.declaration_resolver is not None:
        declarations = resolve_declaration_context(
            resolver=context.declaration_resolver, file_path=file_path
        )
    if local_declarations is not None:
        declarations = DeclarationResolutionContext(
            enums=declarations.enums | local_declarations.enums,
            constants=declarations.constants | local_declarations.constants,
            inaccessible_enums=declarations.inaccessible_enums,
            inaccessible_constants=declarations.inaccessible_constants,
        )
    return expand_authored_sql_with_spans(
        sql=sql,
        file_path=file_path,
        effective_vars=context.effective_vars,
        loaded_macros=context.loaded_macros,
        macro_context=context.macro_context,
        declarations=declarations,
        value_renderer=context.value_renderer,
        collection_rendering=context.collection_rendering,
    )
