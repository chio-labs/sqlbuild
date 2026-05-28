from dataclasses import dataclass

from sqlbuild.adapter.shared.models import SchemaDiffResult
from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class SnowflakeExpressionInferenceProfileTestCase:
    description: str
    expected_sqlglot_dialect: str
    expected_identifier_limit: int
    expected_rule_results: dict[str, InferredNullability]


@dataclass(frozen=True)
class SnowflakeRenderCursorBoundLiteralTestCase:
    description: str
    value: str
    cursor_type: str | None
    expected_literal: str


@dataclass(frozen=True)
class SnowflakeRenderCloneTestCase:
    description: str
    source: str
    target: str
    hard_copy: bool
    expected_statements: tuple[str, ...]
    expected_supports_zero_copy: bool


@dataclass(frozen=True)
class SnowflakeMoveOrCopyRelationTestCase:
    description: str
    source: str
    target: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeRenderIdentifierTestCase:
    description: str
    name: str
    expected_identifier: str


@dataclass(frozen=True)
class SnowflakeSchemaDiffTestCase:
    description: str
    expected_result: SchemaDiffResult


@dataclass(frozen=True)
class SnowflakeRenderPythonFunctionTestCase:
    description: str
    expected_sql: str


@dataclass(frozen=True)
class SnowflakeRenderTableFunctionTestCase:
    description: str
    expected_sql: str


@dataclass(frozen=True)
class SnowflakeQueryColumnNamesTestCase:
    description: str
    cursor_description: tuple[tuple[str], ...]
    expected_columns: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeLoadSeedTestCase:
    description: str
    csv_text: str
    expected_rows: list[tuple[object, ...]]
