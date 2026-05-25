from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PostgresStateBackendLifecycleTestCase:
    description: str
    sqlbuild_version: str
    expected_schema_version: int
    expected_actions_after_backup: tuple[str, ...]
    expected_actions_after_rollback: tuple[str, ...]
    expected_backup_actions: tuple[str, ...]


@dataclass(frozen=True)
class PostgresStateBackendValidationTestCase:
    description: str
    expected_issue_count: int


@dataclass(frozen=True)
class PostgresStateBackendErrorTestCase:
    description: str
    expected_error_type: type[Exception]
    expected_message_fragment: str


@dataclass(frozen=True)
class PostgresStateBackendExplicitRollbackTestCase:
    description: str
    sqlbuild_version: str
    expected_restored_schema_version: int
