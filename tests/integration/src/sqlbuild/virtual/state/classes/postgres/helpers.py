from __future__ import annotations

import uuid
from typing import Any


def build_unique_schema_name(*, prefix: str) -> str:
    suffix: str = uuid.uuid4().hex[:10]
    return f"{prefix}_{suffix}"


def fetch_all(connection: Any, sql: str) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return [tuple(row) for row in cursor.fetchall()]


def qualified_name(*, schema: str, table: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
