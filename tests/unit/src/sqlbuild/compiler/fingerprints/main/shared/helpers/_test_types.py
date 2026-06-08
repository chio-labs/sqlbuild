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
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    run_id: str
    query_hash: str
    schema_fingerprint: str
    query_sql: str
    metadata_json: str
    ts: str
    expected_contains: tuple[str, ...]
