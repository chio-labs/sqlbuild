from dataclasses import dataclass

from sqlbuild.adapter.shared.models import ColumnInfo


@dataclass(frozen=True)
class NormalizeQuerySqlTestCase:
    description: str
    query_sql: str
    expected_normalized: str


@dataclass(frozen=True)
class ComputeQueryHashTestCase:
    description: str
    query_sql: str
    expected_hash: str


@dataclass(frozen=True)
class ComputeQueryHashStabilityTestCase:
    description: str
    query_a: str
    query_b: str
    expected_same_hash: bool


@dataclass(frozen=True)
class ComputeSchemaFingerprintTestCase:
    description: str
    columns: tuple[ColumnInfo, ...]
    expected_fingerprint: str


@dataclass(frozen=True)
class ComputeSchemaFingerprintStabilityTestCase:
    description: str
    columns_a: tuple[ColumnInfo, ...]
    columns_b: tuple[ColumnInfo, ...]
    expected_same_fingerprint: bool


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
