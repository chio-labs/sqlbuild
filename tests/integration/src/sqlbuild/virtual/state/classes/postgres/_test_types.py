from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PostgresConditionalVirtualRefPublishTestCase:
    """Expected conditional virtual-ref publication results."""

    description: str
    expected_stale_publish: bool
    expected_owned_publish: bool
    expected_model_version_hash: str


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
    expected_index_names: tuple[str, ...]


@dataclass(frozen=True)
class PostgresStateBackendTableCreationTestCase:
    description: str
    sqlbuild_version: str
    expected_table_names: tuple[str, ...]
    expected_index_names: tuple[str, ...]


@dataclass(frozen=True)
class PostgresStateBackendCoreRecordsTestCase:
    description: str
    sqlbuild_version: str
    expected_model_name: str
    expected_version_hash: str
    expected_virtual_environment_name: str
    expected_ref_count: int
    expected_ref_count_after_replace: int
    expected_relation_name: str
    expected_replaced_relation_name: str


@dataclass(frozen=True)
class PostgresStateBackendSourceFreshnessTestCase:
    description: str
    sqlbuild_version: str
    virtual_environment_name: str
    expected_source_names: tuple[str, ...]
    expected_source_names_after_replace: tuple[str, ...]


@dataclass(frozen=True)
class PostgresStateBackendSeedRefTestCase:
    description: str
    sqlbuild_version: str
    virtual_environment_name: str
    seed_name: str
    version_hash: str
    identity_metadata_hash: str
    identity_metadata_json_b64: str
    expected_ref_count_after_replace: int


@dataclass(frozen=True)
class PostgresStateBackendPythonNodeIdentityTestCase:
    description: str
    sqlbuild_version: str
    first_virtual_environment_name: str
    second_virtual_environment_name: str
    node_type: str
    node_name: str
    first_version_hash: str
    second_version_hash: str
    expected_ref_versions: tuple[str, str]
    orphan_version_hash: str
    expected_pruned_count: int


@dataclass(frozen=True)
class PostgresStateBackendNodeResultTestCase:
    description: str
    sqlbuild_version: str
    virtual_environment_name: str
    isolated_virtual_environment_name: str
    expected_latest_payload: dict[str, object]
    expected_failed_status: str
    expected_history_count: int
    expected_target_isolated_payload: dict[str, object]
    expected_rollback_row_count: int


@dataclass(frozen=True)
class PostgresStateBackendIndexValidationTestCase:
    description: str
    sqlbuild_version: str
    dropped_index_name: str
    expected_issue_kind: str


@dataclass(frozen=True)
class PostgresStateBackendColumnValidationTestCase:
    description: str
    sqlbuild_version: str
    dropped_table_name: str
    dropped_column_name: str
    expected_issue_kind: str


@dataclass(frozen=True)
class PostgresStateBackendTransactionRollbackTestCase:
    description: str
    sqlbuild_version: str
    virtual_environment_name: str
    model_name: str
    original_version_hash: str
    duplicate_version_hash: str
    expected_ref_count: int


@dataclass(frozen=True)
class PostgresStateBackendLockTestCase:
    description: str
    sqlbuild_version: str
    lock_key: str
    first_owner: str
    second_owner: str
    expected_active_lock_count: int


@dataclass(frozen=True)
class PostgresStateBackendConcurrentLockTestCase:
    description: str
    sqlbuild_version: str
    lock_key: str
    first_owner: str
    second_owner: str
    expected_success_count: int
    expected_active_lock_count: int


@dataclass(frozen=True)
class PostgresStateBackendOperationEventTestCase:
    description: str
    sqlbuild_version: str
    expected_operation_id: str
    expected_virtual_environment_name: str


@dataclass(frozen=True)
class PostgresMicrobatchStateRoundTripTestCase:
    """Expected append-only Postgres microbatch event behavior."""

    description: str
    expected_event_count: int
