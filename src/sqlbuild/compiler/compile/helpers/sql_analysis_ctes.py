"""Polyglot-assisted top-level CTE extraction helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.shared.helpers.polyglot import import_polyglot_sql


def extract_top_level_ctes_with_sql_analysis(
    *, sql: str, file_label: str, context_label: str
) -> tuple[tuple[str, str], ...] | None:
    """Extract top-level CTE aliases and rendered bodies with Polyglot when available."""

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return None
    try:
        parsed: Any = polyglot_module.parse_one(sql, dialect="generic")
    except Exception:
        return None

    with_expression: Any | None = parsed.args.get("with")
    if with_expression is None:
        return None
    if not _is_ceremonial_select(parsed=parsed):
        return None

    ctes: list[tuple[str, str]] = []
    seen_cte_names: set[str] = set()
    for cte in with_expression.get("ctes", ()):
        cte_name: str | None = _cte_name(cte)
        if cte_name is None:
            return None
        if cte_name in seen_cte_names:
            raise CompileInputError(
                f"{context_label} '{file_label}' defines duplicate CTE '{cte_name}'"
            )
        seen_cte_names.add(cte_name)
        body_sql: str | None = _generate_cte_body(polyglot_module=polyglot_module, cte=cte)
        if body_sql is None:
            return None
        ctes.append((cte_name, body_sql))
    return tuple(ctes)


def _is_ceremonial_select(*, parsed: Any) -> bool:
    if parsed.__class__.__name__ != "Select":
        return False
    expressions: list[Any] = list(parsed.expressions)
    if len(expressions) != 1:
        return False
    literal: Any = expressions[0]
    if literal.__class__.__name__ != "Literal" or literal.is_string or str(literal.name) != "1":
        return False
    ignored_args: set[str] = {
        "expressions",
        "leading_comments",
        "with",
    }
    return all(key in ignored_args or _is_empty_arg(value) for key, value in parsed.args.items())


def _cte_name(cte: dict[str, Any]) -> str | None:
    alias: Any | None = cte.get("alias")
    if not isinstance(alias, dict):
        return None
    name: Any | None = alias.get("name")
    return str(name) if name is not None else None


def _generate_cte_body(*, polyglot_module: Any, cte: dict[str, Any]) -> str | None:
    body: Any | None = cte.get("this")
    if body is None:
        return None
    try:
        generated: list[str] = polyglot_module.generate(body, dialect="generic")
    except Exception:
        return None
    if len(generated) != 1:
        return None
    return generated[0]


def _is_empty_arg(value: Any) -> bool:
    return value is None or value is False or value == []
