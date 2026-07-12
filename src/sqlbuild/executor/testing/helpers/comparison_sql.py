"""Polyglot-backed formatting helpers for SQL unit-test comparison SQL."""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from copy import deepcopy
from typing import Any

from sqlbuild.diagnostics.helpers.logging import log_debug_event
from sqlbuild.shared.helpers.sql.polyglot import import_polyglot_sql

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")

_IDENTIFIER_CHAR_PATTERN: re.Pattern[str] = re.compile(r"[^a-zA-Z0-9_]+")
_BACKTICK_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"`[^`]+`(?:\s*\.\s*`[^`]+`)*")


def lift_step_ctes(
    *, sql: str, lifted_ctes: OrderedDict[str, str], sql_analysis_enabled: bool = True
) -> tuple[str, OrderedDict[str, str]]:
    """Lift a step's top-level CTEs into the shared comparison query when possible."""

    if not sql_analysis_enabled:
        return sql, lifted_ctes
    split_sql: tuple[tuple[tuple[str, str], ...], str] | None = _split_top_level_with(sql)
    if split_sql is None:
        return sql, lifted_ctes
    step_ctes: tuple[tuple[str, str], ...]
    body_sql: str
    step_ctes, body_sql = split_sql
    cte_name: str
    cte_sql: str
    for cte_name, cte_sql in step_ctes:
        existing_name: str | None = _existing_cte_name(lifted_ctes=lifted_ctes, cte_name=cte_name)
        existing_sql: str | None = lifted_ctes.get(existing_name) if existing_name else None
        if existing_sql is not None and existing_sql != cte_sql:
            return sql, lifted_ctes
    updated_ctes: OrderedDict[str, str] = OrderedDict(lifted_ctes)
    for cte_name, cte_sql in step_ctes:
        existing_name = _existing_cte_name(lifted_ctes=updated_ctes, cte_name=cte_name)
        if existing_name is None:
            updated_ctes[cte_name] = cte_sql
    return body_sql, updated_ctes


def format_sql(
    *, sql: str, sql_analysis_dialect: str | None = None, sql_analysis_enabled: bool = True
) -> str:
    """Format generated comparison SQL when Polyglot is available."""

    if not sql_analysis_enabled:
        return sql
    protected_sql: str = sql
    protected_identifiers: dict[str, str] = {}
    if sql_analysis_dialect in {"bigquery", "databricks"} and "`" in sql:
        protected_sql, protected_identifiers = _protect_backtick_identifiers(sql)
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return sql
    try:
        formatted_sql: str = str(
            polyglot_module.format(
                protected_sql,
                dialect=sql_analysis_dialect or "generic",
            )
        )
        return _restore_protected_identifiers(
            sql=formatted_sql,
            protected_identifiers=protected_identifiers,
        )
    except Exception:
        return sql


def unique_cte_suffix(
    *, model_name: str, cte_name_counts: dict[str, int]
) -> tuple[str, dict[str, int]]:
    """Return a readable generated CTE suffix for a chain step and updated counts."""

    base_suffix: str = _sanitize_cte_suffix(model_name)
    updated_counts: dict[str, int] = dict(cte_name_counts)
    count: int = updated_counts.get(base_suffix, 0) + 1
    updated_counts[base_suffix] = count
    if count == 1:
        return base_suffix, updated_counts
    return f"{base_suffix}_{count}", updated_counts


def _split_top_level_with(sql: str) -> tuple[tuple[tuple[str, str], ...], str] | None:
    """Split top-level WITH CTEs from a SQL statement with Polyglot if available."""

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return None
    protected_sql: str = sql
    protected_identifiers: dict[str, str] = {}
    if "`" in sql:
        protected_sql, protected_identifiers = _protect_backtick_identifiers(sql)

    try:
        parsed: Any = polyglot_module.parse_one(protected_sql, dialect="generic")
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="comparison SQL top-level WITH parse failed; falling back",
            sqlbuild_error=str(error),
        )
        return None

    parsed_dict: dict[str, Any] = parsed.to_dict()
    select_dict: dict[str, Any] | None = parsed_dict.get("select")
    if select_dict is None:
        return None
    parsed_with: dict[str, Any] | None = select_dict.get("with")
    if parsed_with is None:
        return None

    cte_parts: list[tuple[str, str]] = []
    cte: dict[str, Any]
    for cte in parsed_with.get("ctes", ()):
        alias: Any | None = cte.get("alias")
        if not isinstance(alias, dict):
            return None
        name: Any | None = alias.get("name")
        body: Any | None = cte.get("this")
        if name is None or body is None:
            return None
        cte_sql: str | None = _generate_one(polyglot_module=polyglot_module, expression=body)
        if cte_sql is None:
            return None
        cte_parts.append(
            (
                str(name),
                _restore_protected_identifiers(
                    sql=cte_sql,
                    protected_identifiers=protected_identifiers,
                ),
            )
        )

    without_with: dict[str, Any] = deepcopy(parsed_dict)
    without_with["select"]["with"] = None
    body_sql: str | None = _generate_one(polyglot_module=polyglot_module, expression=without_with)
    if body_sql is None:
        return None
    return (
        tuple(cte_parts),
        _restore_protected_identifiers(
            sql=body_sql,
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


def _generate_one(*, polyglot_module: Any, expression: Any) -> str | None:
    try:
        generated: list[str] = polyglot_module.generate(expression, dialect="generic")
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="comparison SQL generation failed; falling back",
            sqlbuild_error=str(error),
        )
        return None
    if len(generated) != 1:
        return None
    return generated[0]


def _protect_backtick_identifiers(sql: str) -> tuple[str, dict[str, str]]:
    protected_identifiers: dict[str, str] = {}
    protected_sql_parts: list[str] = []
    previous_end: int = 0
    match: re.Match[str]
    for match in _BACKTICK_IDENTIFIER_PATTERN.finditer(sql):
        placeholder: str = f"SQB_PROTECTED_IDENTIFIER_{len(protected_identifiers)}"
        protected_identifiers[placeholder] = match.group(0)
        protected_sql_parts.extend((sql[previous_end : match.start()], placeholder))
        previous_end = match.end()
    protected_sql_parts.append(sql[previous_end:])
    return "".join(protected_sql_parts), protected_identifiers


def _restore_protected_identifiers(*, sql: str, protected_identifiers: dict[str, str]) -> str:
    restored_sql: str = sql
    placeholder: str
    identifier: str
    for placeholder, identifier in protected_identifiers.items():
        restored_sql = restored_sql.replace(placeholder, identifier)
    return restored_sql
