from __future__ import annotations

from sqlbuild._native import SqlValue, normalize_sql_value


def typed_sql_value(raw_value: object) -> SqlValue:
    return normalize_sql_value(raw_value=raw_value, context="test value")
