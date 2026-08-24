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
class DuckDbStateBackendAtomicRefUpdateTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    virtual_environment_name: str
    model_name: str
    seed_name: str
    expected_original_model_hash: str
    expected_original_seed_hash: str
    expected_updated_model_hash: str
    expected_updated_seed_hash: str
    expected_duplicate_seed_hash: str


@dataclass(frozen=True)
class DuckDbStateBackendSourceFreshnessTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    virtual_environment_name: str
    expected_source_names: tuple[str, ...]
    expected_source_names_after_replace: tuple[str, ...]


@dataclass(frozen=True)
class DuckDbStateBackendSeedRefTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    virtual_environment_name: str
    seed_name: str
    version_hash: str
    identity_metadata_hash: str
    identity_metadata_json_b64: str
    replacement_version_hash: str
    expected_ref_count_after_replace: int


@dataclass(frozen=True)
class DuckDbStateBackendPythonNodeIdentityTestCase:
    description: str
    schema: str
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
class DuckDbStateBackendNodeResultTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    virtual_environment_name: str
    isolated_virtual_environment_name: str
    expected_latest_payload: dict[str, object]
    expected_failed_status: str
    expected_history_count: int
    expected_target_isolated_payload: dict[str, object]
    expected_rollback_row_count: int


@dataclass(frozen=True)
class DuckDbStateBackendIndexValidationTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    dropped_index_name: str
    expected_issue_kind: str


@dataclass(frozen=True)
class DuckDbStateBackendColumnValidationTestCase:
    description: str
    schema: str
    sqlbuild_version: str
    dropped_table_name: str
    dropped_column_name: str
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


@dataclass(frozen=True)
class MicrobatchStateRoundTripTestCase:
    """Expected append-only microbatch event persistence behavior."""

    description: str
    expected_event_count: int
