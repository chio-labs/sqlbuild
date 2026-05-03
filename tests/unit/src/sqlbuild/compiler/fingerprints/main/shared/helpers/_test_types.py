from dataclasses import dataclass


@dataclass(frozen=True)
class BuildQualifiedTableNameTestCase:
    description: str
    database: str | None
    schema: str
    expected_name: str


@dataclass(frozen=True)
class BuildCreateTableSqlTestCase:
    description: str
    database: str | None
    schema: str
    expected_contains: tuple[str, ...]


@dataclass(frozen=True)
class BuildReadAllSqlTestCase:
    description: str
    database: str | None
    schema: str
    expected_contains: tuple[str, ...]


@dataclass(frozen=True)
class BuildInsertSqlTestCase:
    description: str
    database: str | None
    schema: str
    model_name: str
    run_id: str
    query_hash: str
    ast_hash: str | None
    schema_fingerprint: str
    query_sql: str
    ts: str
    expected_contains: tuple[str, ...]
