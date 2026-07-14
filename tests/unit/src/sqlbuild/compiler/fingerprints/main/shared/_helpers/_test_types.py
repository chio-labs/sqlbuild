from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class BuildQualifiedTableNameTestCase:
    description: str
    database: str | None
    schema: str
    render_qualified_name: Callable[..., str | None]
    expected_name: str


@dataclass(frozen=True)
class BuildCreateTableSqlTestCase:
    description: str
    database: str | None
    schema: str
    expected_contains: tuple[str, ...]
    transient: bool = False


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
    node_type: str
    node_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    run_id: str
    definition_hash: str
    version_hash: str
    schema_fingerprint: str
    definition: str
    metadata_json: str
    ts: str
    expected_contains: tuple[str, ...]
