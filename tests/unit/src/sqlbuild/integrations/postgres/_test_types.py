from dataclasses import dataclass

from sqlbuild.adapter.shared.models import ColumnInfo, SchemaDiffResult


@dataclass(frozen=True)
class PostgresRenderCreateTableAsTestCase:
    description: str
    target: str
    sql: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class PostgresRenderRenameTestCase:
    description: str
    source: str
    target: str
    expected_statement: str


@dataclass(frozen=True)
class PostgresRenderSwapTestCase:
    description: str
    left: str
    right: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class PostgresDescribeRelationTestCase:
    description: str
    relation: str
    cursor_rows: tuple[tuple[str, str], ...]
    expected_columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class PostgresAdapterDefaultsTestCase:
    description: str
    expected_default_schema: str
    expected_default_database: str | None
    expected_sqlglot_dialect: str | None
    expected_identifier_length: int


@dataclass(frozen=True)
class PostgresLoadSeedTestCase:
    description: str
    csv_text: str
    expected_rows: list[tuple[object, ...]]


@dataclass(frozen=True)
class PostgresSchemaDiffTestCase:
    description: str
    expected_result: SchemaDiffResult
