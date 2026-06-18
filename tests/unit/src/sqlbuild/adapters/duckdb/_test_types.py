from dataclasses import dataclass

from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class DuckDbExpressionInferenceProfileTestCase:
    description: str
    expected_sql_analysis_dialect: str
    expected_rule_results: dict[str, InferredNullability]


@dataclass(frozen=True)
class DuckDbRenderCursorBoundLiteralTestCase:
    description: str
    value: str
    cursor_type: str | None
    expected_literal: str


@dataclass(frozen=True)
class DuckDbRenderIdentifierTestCase:
    description: str
    name: str
    expected_identifier: str


@dataclass(frozen=True)
class DuckDbRenderTableFunctionTestCase:
    description: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class DuckDbMetadataSqlTestCase:
    description: str
    database: str
    schema: str
    name: str
    expected_sql: tuple[str, ...]


@dataclass(frozen=True)
class DuckDbRelationMaxCursorTestCase:
    description: str
    expected_populated_value: object
    expected_empty_value: object | None


@dataclass(frozen=True)
class DuckDbPruneSqlTestCase:
    description: str
    database: str | None
    schema: str
    retain_versions: int
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DuckDbRenderSwapTestCase:
    description: str
    left: str
    right: str
    expected_statements: tuple[str, ...]
