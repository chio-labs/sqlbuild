"""SQLGlot-backed formatting helpers for SQL unit-test comparison SQL."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from sqlbuild.shared.helpers.sqlglot import import_sqlglot

_IDENTIFIER_CHAR_PATTERN: re.Pattern[str] = re.compile(r"[^a-zA-Z0-9_]+")
_DATABRICKS_BACKTICK_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(
    r"`[^`]+`(?:\s*\.\s*`[^`]+`)*"
)


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
        existing_name: str | None = _existing_cte_name(lifted_ctes=lifted_ctes, cte_name=cte_name)
        existing_sql: str | None = lifted_ctes.get(existing_name) if existing_name else None
        if existing_sql is not None and existing_sql != cte_sql:
            return sql
    for cte_name, cte_sql in step_ctes:
        existing_name = _existing_cte_name(lifted_ctes=lifted_ctes, cte_name=cte_name)
        if existing_name is None:
            lifted_ctes[cte_name] = cte_sql
    return body_sql


def format_sql(
    sql: str, *, sqlglot_dialect: str | None = None, sqlglot_enabled: bool = True
) -> str:
    """Format generated comparison SQL when SQLGlot is available."""

    if not sqlglot_enabled:
        return sql
    protected_sql: str = sql
    protected_identifiers: dict[str, str] = {}
    if sqlglot_dialect == "databricks" and "`" in sql:
        protected_sql, protected_identifiers = _protect_databricks_backtick_identifiers(sql)
    sqlglot_module: Any | None = import_sqlglot()
    if sqlglot_module is None:
        return sql
    try:
        if sqlglot_dialect is None:
            formatted_sql: str = sqlglot_module.parse_one(protected_sql).sql(pretty=True)
            return _restore_protected_identifiers(
                sql=formatted_sql, protected_identifiers=protected_identifiers
            )
        formatted_sql = sqlglot_module.parse_one(protected_sql, read=sqlglot_dialect).sql(
            pretty=True,
            dialect=sqlglot_dialect,
        )
        return _restore_protected_identifiers(
            sql=formatted_sql, protected_identifiers=protected_identifiers
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
    protected_sql: str = sql
    protected_identifiers: dict[str, str] = {}
    if "`" in sql:
        protected_sql, protected_identifiers = _protect_databricks_backtick_identifiers(sql)

    try:
        parsed: Any = sqlglot_module.parse_one(protected_sql)
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
        cte_parts.append(
            (
                str(alias),
                _restore_protected_identifiers(
                    sql=cte.this.sql(pretty=False),
                    protected_identifiers=protected_identifiers,
                ),
            )
        )

    parsed_without_with: Any = parsed.copy()
    parsed_without_with.set("with_", None)
    return (
        tuple(cte_parts),
        _restore_protected_identifiers(
            sql=parsed_without_with.sql(pretty=False),
            protected_identifiers=protected_identifiers,
        ),
    )


def _sanitize_cte_suffix(model_name: str) -> str:
    """Convert a model name into a safe unquoted SQL identifier suffix."""

    suffix: str = _IDENTIFIER_CHAR_PATTERN.sub("_", model_name).strip("_").lower()
    if not suffix:
        return "model"
    if suffix[0].isdigit():
        return f"model_{suffix}"
    return suffix


def _existing_cte_name(*, lifted_ctes: OrderedDict[str, str], cte_name: str) -> str | None:
    normalized_name: str = cte_name.lower()
    existing_name: str
    for existing_name in lifted_ctes:
        if existing_name.lower() == normalized_name:
            return existing_name
    return None


def _protect_databricks_backtick_identifiers(sql: str) -> tuple[str, dict[str, str]]:
    protected_identifiers: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        placeholder: str = f"SQB_PROTECTED_IDENTIFIER_{len(protected_identifiers)}"
        protected_identifiers[placeholder] = match.group(0)
        return placeholder

    return _DATABRICKS_BACKTICK_IDENTIFIER_PATTERN.sub(_replace, sql), protected_identifiers


def _restore_protected_identifiers(*, sql: str, protected_identifiers: dict[str, str]) -> str:
    restored_sql: str = sql
    placeholder: str
    identifier: str
    for placeholder, identifier in protected_identifiers.items():
        restored_sql = restored_sql.replace(placeholder, identifier)
    return restored_sql
