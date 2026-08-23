from dataclasses import dataclass

from sqlbuild.adapter.contract.models import ColumnInfo, SchemaDiffResult


@dataclass(frozen=True)
class PostgresMergeExclusionTestCase:
    description: str
    expected_update_clause: str
    expected_insert_clause: str


@dataclass(frozen=True)
class PostgresRenderCreateTableAsTestCase:
    description: str
    target: str
    sql: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class PostgresRenderCreateFunctionTestCase:
    description: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class PostgresRenderRenameTestCase:
    description: str
    source: str
    target: str
    expected_statement: str


@dataclass(frozen=True)
class PostgresMoveOrCopyRelationTestCase:
    description: str
    source: str
    target: str
    expected_statements: tuple[str, ...]


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
    expected_sql_analysis_dialect: str | None
    expected_identifier_length: int


@dataclass(frozen=True)
class PostgresRenderIdentifierTestCase:
    description: str
    name: str
    expected_identifier: str


@dataclass(frozen=True)
class PostgresLoadSeedTestCase:
    description: str
    csv_text: str
    expected_rows: list[tuple[object, ...]]


@dataclass(frozen=True)
class PostgresSchemaDiffTestCase:
    description: str
    expected_result: SchemaDiffResult


@dataclass(frozen=True)
class PostgresIndexSqlTestCase:
    description: str
    database: str | None
    schema: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class PostgresLatestReadSqlTestCase:
    description: str
    database: str | None
    schema: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PostgresPruneSqlTestCase:
    description: str
    database: str | None
    schema: str
    retain_versions: int
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PostgresRenderSourceFreshnessQueryTestCase:
    description: str
    column: str
    source_relation: str
    source_is_subquery: bool
    where_sql: str
    expected_sql: str
