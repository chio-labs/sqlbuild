"""Reference analysis names, lineage resource types, qualified-reference scans and placeholders."""

from __future__ import annotations

import sqlbuild._native as _native


def table_function_analysis_name(function_name: str) -> str:
    """Return the stable relation stub used to analyze a table-function call."""

    return f"__sqlbuild_table_function_{function_name}"


def substitute_placeholder_defaults(*, query_sql: str, placeholders: dict[str, str]) -> str:
    """Replace @@@name tokens with their default values for SQL analysis parsing."""

    if not placeholders:
        return query_sql
    return _native.substitute_placeholder_defaults(query_sql, list(placeholders.items()))
