from dataclasses import dataclass


@dataclass(frozen=True)
class ProxyCompatibilityCase:
    description: str
    expected_row_factory: str
    expected_autocommit: bool
    expected_rows: tuple[tuple[int, str], ...]
    expected_commit_count: int
    expected_rollback_count: int


@dataclass(frozen=True)
class DuckDbConnectionProxyCase:
    description: str
    sql: str
    expected_rows: tuple[tuple[int, ...], ...]
