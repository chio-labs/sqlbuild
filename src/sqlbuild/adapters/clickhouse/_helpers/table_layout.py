"""Render a model's physical table layout as ClickHouse table clauses."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from sqlbuild.adapters.clickhouse._helpers.type_text import quote_string
from sqlbuild.adapters.clickhouse.constants import DEFAULT_TABLE_ENGINE, EMPTY_SORTING_KEY


def render_table_layout(layout: dict[str, Any]) -> str:
    """Return the ENGINE, ORDER BY, PARTITION BY, PRIMARY KEY and SETTINGS clauses."""

    clauses: list[str] = [
        f"ENGINE = {str(layout.get('engine') or DEFAULT_TABLE_ENGINE).strip()}",
        f"ORDER BY {_key_tuple(layout.get('order_by')) or EMPTY_SORTING_KEY}",
    ]
    partition_by: object = layout.get("partition_by")
    if partition_by:
        clauses.append(f"PARTITION BY {str(partition_by).strip()}")
    primary_key: str | None = _key_tuple(layout.get("primary_key"))
    if primary_key:
        clauses.append(f"PRIMARY KEY {primary_key}")
    settings: dict[str, object] = dict(layout.get("table_settings") or {})
    if settings:
        clauses.append(
            "SETTINGS "
            + ", ".join(f"{name} = {_setting_value(value)}" for name, value in settings.items())
        )
    return " ".join(clauses)


def _key_tuple(value: object) -> str | None:
    items: Iterable[object] = (value,) if isinstance(value, str) else cast(Any, value) or ()
    expressions: list[str] = [str(item) for item in items]
    expressions = [expression.strip() for expression in expressions if expression.strip()]
    return f"({', '.join(expressions)})" if expressions else None


def _setting_value(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return quote_string(str(value))
