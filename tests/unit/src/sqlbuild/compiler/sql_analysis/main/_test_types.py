from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaValidationScopeTestCase:
    description: str
    query_sql: str
    schema: dict[str, dict[str, str]]
    dialects: tuple[str, ...]
    expected_diagnostic_count: int
