from dataclasses import dataclass


@dataclass(frozen=True)
class SqlServerAdapterDefaultsTestCase:
    description: str
    expected_default_schema: str
    expected_default_database: str | None
    expected_sqlglot_dialect: str | None
    expected_identifier_length: int


@dataclass(frozen=True)
class SqlServerRenderIdentifierTestCase:
    description: str
    name: str
    expected_identifier: str


@dataclass(frozen=True)
class SqlServerRenderCreateTableAsTestCase:
    description: str
    target: str
    sql: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class SqlServerRenderCreateFunctionTestCase:
    description: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class SqlServerRenderCreateSchemaTestCase:
    description: str
    schema: str
    expected_statement: str


@dataclass(frozen=True)
class SqlServerMoveOrCopyRelationTestCase:
    description: str
    source: str
    target: str
    expected_statements: tuple[str, ...]
