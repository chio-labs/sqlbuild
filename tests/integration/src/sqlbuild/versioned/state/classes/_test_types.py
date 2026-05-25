from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DuckDbStateBackendLifecycleTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    expected_schema_version: int
    expected_backup_prefix: str


@dataclass(frozen=True)
class DuckDbStateBackendValidationTestCase:
    description: str
    schema: str
    expected_issue_count: int


@dataclass(frozen=True)
class DuckDbStateBackendRollbackTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    expected_restored_sqlbuild_version: str


@dataclass(frozen=True)
class DuckDbStateBackendErrorTestCase:
    description: str
    schema: str
    expected_error_type: type[Exception]
    expected_message_fragment: str


@dataclass(frozen=True)
class DuckDbStateBackendEventTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    expected_actions_after_backup: tuple[str, ...]
    expected_actions_after_rollback: tuple[str, ...]
    expected_backup_actions: tuple[str, ...]


@dataclass(frozen=True)
class DuckDbStateBackendIdempotencyTestCase:
    description: str
    schema: str
    first_sqlbuild_version: str
    second_sqlbuild_version: str
    expected_schema_version_rows: int
    expected_latest_sqlbuild_version: str
