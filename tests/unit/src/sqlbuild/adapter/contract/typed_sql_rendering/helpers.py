from __future__ import annotations

from sqlbuild.sql_values.main.normalize import normalize_sql_value
from sqlbuild.sql_values.models import SqlValue


def typed_sql_value(raw_value: object) -> SqlValue:
    return normalize_sql_value(raw_value=raw_value, context="test value")
