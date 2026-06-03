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
    expected_index_names: tuple[str, ...]


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


@dataclass(frozen=True)
class DuckDbStateBackendTableCreationTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    expected_table_names: tuple[str, ...]
    expected_index_names: tuple[str, ...]


@dataclass(frozen=True)
class DuckDbStateBackendCoreRecordsTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    expected_model_name: str
    expected_version_hash: str
    expected_virtual_environment_name: str
    expected_ref_count: int
    expected_ref_count_after_replace: int
    expected_relation_name: str
    expected_replaced_relation_name: str


@dataclass(frozen=True)
class DuckDbStateBackendSourceFreshnessTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    virtual_environment_name: str
    expected_source_names: tuple[str, ...]
    expected_source_names_after_replace: tuple[str, ...]


@dataclass(frozen=True)
class DuckDbStateBackendIndexValidationTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    dropped_index_name: str
    expected_issue_kind: str


@dataclass(frozen=True)
class DuckDbStateBackendTransactionRollbackTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    virtual_environment_name: str
    model_name: str
    original_version_hash: str
    duplicate_version_hash: str
    expected_ref_count: int


@dataclass(frozen=True)
class DuckDbStateBackendLockTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    lock_key: str
    first_owner: str
    second_owner: str
    expected_active_lock_count: int


@dataclass(frozen=True)
class DuckDbStateBackendConcurrentLockTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    lock_key: str
    first_owner: str
    second_owner: str
    expected_success_count: int
    expected_active_lock_count: int


@dataclass(frozen=True)
class DuckDbStateBackendOperationEventTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    expected_operation_id: str
    expected_virtual_environment_name: str
