from dataclasses import dataclass

from sqlbuild.adapter.shared.models import SchemaDiffResult


@dataclass(frozen=True)
class SnowflakeRenderCursorBoundLiteralTestCase:
    description: str
    value: str
    cursor_type: str | None
    expected_literal: str


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
