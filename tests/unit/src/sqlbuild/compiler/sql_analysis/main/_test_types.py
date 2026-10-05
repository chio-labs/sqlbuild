from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.compiler.sql_analysis.types import NativeProjectCatalog


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
class ExactColumnCatalogValidationTestCase:
    description: str
    query_sql: str
    schema: dict[str, dict[str, str]]
    expected_messages: tuple[str, ...]


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


@dataclass(frozen=True)
class NormalizationBatchTestCase:
    description: str
    dialect: str
    requests: tuple[tuple[str, dict[str, str], dict[str, str]], ...]
    catalog: Callable[[str], NativeProjectCatalog | None]
    expected_stubbed_sql: str


@dataclass(frozen=True)
class NormalizationBatchFailureTestCase:
    description: str
    dialect: str
    before: tuple[str, ...]
    failing: str
    after: tuple[str, ...]
    catalog: Callable[[str], NativeProjectCatalog | None]
    expected_error_type: type[Exception]
    expected_result_types: tuple[str, ...]
