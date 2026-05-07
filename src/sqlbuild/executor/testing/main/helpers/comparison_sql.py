"""SQLGlot-backed formatting helpers for SQL unit-test comparison SQL."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from sqlbuild.shared.helpers.sqlglot import import_sqlglot

_IDENTIFIER_CHAR_PATTERN: re.Pattern[str] = re.compile(r"[^a-zA-Z0-9_]+")


def lift_step_ctes(
    sql: str, lifted_ctes: OrderedDict[str, str], *, sqlglot_enabled: bool = True
) -> str:
    """Lift a step's top-level CTEs into the shared comparison query when possible."""

    if not sqlglot_enabled:
        return sql
    split_sql: tuple[tuple[tuple[str, str], ...], str] | None = _split_top_level_with(sql)
    if split_sql is None:
        return sql
    step_ctes: tuple[tuple[str, str], ...]
    body_sql: str
    step_ctes, body_sql = split_sql
    cte_name: str
    cte_sql: str
    for cte_name, cte_sql in step_ctes:
        existing_sql: str | None = lifted_ctes.get(cte_name)
        if existing_sql is not None and existing_sql != cte_sql:
            return sql
    for cte_name, cte_sql in step_ctes:
        lifted_ctes.setdefault(cte_name, cte_sql)
    return body_sql


def format_sql(
    sql: str, *, sqlglot_dialect: str | None = None, sqlglot_enabled: bool = True
) -> str:
    """Format generated comparison SQL when SQLGlot is available."""

    if not sqlglot_enabled:
        return sql
    sqlglot_module: Any | None = import_sqlglot()
    if sqlglot_module is None:
        return sql
    try:
        if sqlglot_dialect is None:
            return sqlglot_module.parse_one(sql).sql(pretty=True)
        return sqlglot_module.parse_one(sql, read=sqlglot_dialect).sql(
            pretty=True,
            dialect=sqlglot_dialect,
        )
    except Exception:
        return sql


def unique_cte_suffix(*, model_name: str, cte_name_counts: dict[str, int]) -> str:
    """Return a readable generated CTE suffix for a chain step."""

    base_suffix: str = _sanitize_cte_suffix(model_name)
    count: int = cte_name_counts.get(base_suffix, 0) + 1
    cte_name_counts[base_suffix] = count
    if count == 1:
        return base_suffix
    return f"{base_suffix}_{count}"


def _split_top_level_with(sql: str) -> tuple[tuple[tuple[str, str], ...], str] | None:
    """Split top-level WITH CTEs from a SQL statement with SQLGlot if available."""

    sqlglot_module: Any | None = import_sqlglot()
    if sqlglot_module is None:
        return None

    try:
        parsed: Any = sqlglot_module.parse_one(sql)
    except Exception:
        return None

    parsed_with: Any | None = parsed.args.get("with_")
    if parsed_with is None:
        return None

    cte_parts: list[tuple[str, str]] = []
    cte: Any
    for cte in parsed_with.expressions:
        alias: Any | None = getattr(cte, "alias", None)
        if alias is None:
            return None
        cte_parts.append((str(alias), cte.this.sql(pretty=False)))

    parsed_without_with: Any = parsed.copy()
    parsed_without_with.set("with_", None)
    return tuple(cte_parts), parsed_without_with.sql(pretty=False)


def _sanitize_cte_suffix(model_name: str) -> str:
    """Convert a model name into a safe unquoted SQL identifier suffix."""

    suffix: str = _IDENTIFIER_CHAR_PATTERN.sub("_", model_name).strip("_").lower()
    if not suffix:
        return "model"
    if suffix[0].isdigit():
        return f"model_{suffix}"
    return suffix
