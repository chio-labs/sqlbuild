from dataclasses import dataclass


@dataclass(frozen=True)
class BuildSourceFreshnessSqlTestCase:
    description: str
    database: str | None
    schema: str
    expected_contains: tuple[str, ...]
    transient: bool = False


@dataclass(frozen=True)
class BuildSourceFreshnessInsertSqlTestCase:
    description: str
    database: str | None
    schema: str
    source_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    run_id: str
    strategy: str
    value_kind: str
    data_version: str | None
    data_version_hash: str
    observed_at: str
    expected_contains: tuple[str, ...]
