"""SQLGlot-assisted top-level CTE extraction helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.shared.helpers.sqlglot import import_sqlglot, import_sqlglot_expressions


def extract_top_level_ctes_with_sqlglot(
    *, sql: str, file_label: str, context_label: str
) -> tuple[tuple[str, str], ...] | None:
    """Extract top-level CTE aliases and rendered bodies with SQLGlot when available."""

    sqlglot_module: Any | None = import_sqlglot()
    expressions_module: Any | None = import_sqlglot_expressions()
    if sqlglot_module is None or expressions_module is None:
        return None
    try:
        parsed: Any = sqlglot_module.parse_one(sql)
    except Exception:
        return None

    with_expression: Any | None = parsed.args.get("with_")
    if with_expression is None:
        return None
    if not _is_ceremonial_select(parsed=parsed, expressions_module=expressions_module):
        return None

    ctes: list[tuple[str, str]] = []
    seen_cte_names: set[str] = set()
    for cte in with_expression.expressions:
        cte_name: str = str(cte.alias_or_name)
        if cte_name in seen_cte_names:
            raise CompileInputError(
                f"{context_label} '{file_label}' defines duplicate CTE '{cte_name}'"
            )
        seen_cte_names.add(cte_name)
        ctes.append((cte_name, cte.this.sql(pretty=False)))
    return tuple(ctes)


def _is_ceremonial_select(*, parsed: Any, expressions_module: Any) -> bool:
    if not isinstance(parsed, expressions_module.Select):
        return False
    expressions: list[Any] = list(parsed.expressions)
    if len(expressions) != 1:
        return False
    literal: Any = expressions[0]
    if not (
        isinstance(literal, expressions_module.Literal)
        and not literal.is_string
        and str(literal.this) == "1"
    ):
        return False
    allowed_args: set[str] = {
        "kind",
        "hint",
        "expressions",
        "limit",
        "exclude",
        "operation_modifiers",
        "with_",
    }
    return all(key in allowed_args or value is None for key, value in parsed.args.items())
