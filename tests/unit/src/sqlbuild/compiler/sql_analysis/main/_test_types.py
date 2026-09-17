from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaValidationScopeTestCase:
    description: str
    query_sql: str
    schema: dict[str, dict[str, str]]
    dialects: tuple[str, ...]
    expected_diagnostic_count: int


@dataclass(frozen=True)
class PolyglotSqlNormalizationTestCase:
    description: str
    sql: str
    dialect: str | None
    expected_sql: str
