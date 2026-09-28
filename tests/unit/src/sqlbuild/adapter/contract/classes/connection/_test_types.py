from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionContractCase:
    description: str
    expected_abstract: bool


@dataclass(frozen=True)
class SqlExecutionFailureCase:
    description: str
    sql: str
    expected_error: str


@dataclass(frozen=True)
class NestedTransactionCase:
    description: str
    fail_after_inner: bool
    expected_tables: tuple[str, ...]
