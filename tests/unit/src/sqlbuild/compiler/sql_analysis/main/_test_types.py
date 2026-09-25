from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticDiagnosticMappingCase:
    description: str
    expected_codes: tuple[str, ...]


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


@dataclass(frozen=True)
class PolyglotDefaultGuardTestCase:
    description: str
    function_depth: int
    expected_kind: str


@dataclass(frozen=True)
class PolyglotExplicitGuardTestCase:
    description: str
    function_depth: int
    maximum_function_depth: int
    expected_error_pattern: str
