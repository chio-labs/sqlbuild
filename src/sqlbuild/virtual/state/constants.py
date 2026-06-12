"""Virtual state store constants."""

from __future__ import annotations

from sqlbuild.virtual.state.types import StateColumnType

CURRENT_STATE_SCHEMA_VERSION: int = 1

STATE_VERSION_TABLE: str = "state_versions"
MODEL_VERSION_TABLE: str = "model_versions"
FUNCTION_VERSION_TABLE: str = "function_versions"
SEED_VERSION_TABLE: str = "seed_versions"
PHYSICAL_RELATION_TABLE: str = "physical_relations"
PHYSICAL_RELATION_ANCESTRY_TABLE: str = "physical_relation_ancestry"
VIRTUAL_ENVIRONMENT_TABLE: str = "virtual_environments"
VIRTUAL_ENVIRONMENT_MODEL_REF_TABLE: str = "virtual_environment_model_refs"
VIRTUAL_ENVIRONMENT_FUNCTION_REF_TABLE: str = "virtual_environment_function_refs"
VIRTUAL_ENVIRONMENT_SEED_REF_TABLE: str = "virtual_environment_seed_refs"
SOURCE_FRESHNESS_OBSERVATION_TABLE: str = "source_freshness_observations"
VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE: str = "virtual_environment_checkpoints"
VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE: str = "virtual_environment_checkpoint_model_refs"
VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE: str = (
    "virtual_environment_checkpoint_function_refs"
)
VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE: str = "virtual_environment_checkpoint_seed_refs"
LOCK_TABLE: str = "locks"
STATE_MIGRATION_LOCK_KEY: str = "state_migration"
STATE_OPERATION_TABLE: str = "state_operations"
PLAN_RUN_TABLE: str = "plan_runs"
VIRTUAL_ENVIRONMENT_MODEL_REF_EVENT_TABLE: str = "virtual_environment_model_ref_events"
RECONCILE_EVENT_TABLE: str = "reconcile_events"
STATE_MIGRATION_EVENTS_TABLE: str = "state_migration_events"
STATE_OPERATION_EVENT_TABLE: str = "state_operation_events"

STATE_TABLES: tuple[str, ...] = (
    STATE_VERSION_TABLE,
    MODEL_VERSION_TABLE,
    FUNCTION_VERSION_TABLE,
    SEED_VERSION_TABLE,
    PHYSICAL_RELATION_TABLE,
    PHYSICAL_RELATION_ANCESTRY_TABLE,
    VIRTUAL_ENVIRONMENT_TABLE,
    VIRTUAL_ENVIRONMENT_MODEL_REF_TABLE,
    VIRTUAL_ENVIRONMENT_FUNCTION_REF_TABLE,
    VIRTUAL_ENVIRONMENT_SEED_REF_TABLE,
    SOURCE_FRESHNESS_OBSERVATION_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE,
    LOCK_TABLE,
    STATE_OPERATION_TABLE,
    PLAN_RUN_TABLE,
    VIRTUAL_ENVIRONMENT_MODEL_REF_EVENT_TABLE,
    RECONCILE_EVENT_TABLE,
    STATE_MIGRATION_EVENTS_TABLE,
    STATE_OPERATION_EVENT_TABLE,
)

STATE_VERSION_COLUMNS: dict[str, StateColumnType] = {
    "schema_version": StateColumnType.INTEGER,
    "sqlbuild_version": StateColumnType.TEXT,
    "updated_at": StateColumnType.TIMESTAMP,
}

STATE_MIGRATION_EVENT_COLUMNS: dict[str, StateColumnType] = {
    "event_id": StateColumnType.TEXT,
    "action": StateColumnType.TEXT,
    "backup_id": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "message": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
}

MODEL_VERSION_COLUMNS: dict[str, StateColumnType] = {
    "model_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
    "definition_identity_hash": StateColumnType.TEXT,
    "identity_metadata_hash": StateColumnType.TEXT,
    "definition_text_b64": StateColumnType.TEXT,
    "identity_metadata_json_b64": StateColumnType.TEXT,
    "compiled_sql_b64": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
    "updated_at": StateColumnType.TIMESTAMP,
}

FUNCTION_VERSION_COLUMNS: dict[str, StateColumnType] = {
    "function_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
    "language": StateColumnType.TEXT,
    "returns": StateColumnType.TEXT,
    "arguments_json_b64": StateColumnType.TEXT,
    "return_columns_json_b64": StateColumnType.TEXT,
    "packages_json_b64": StateColumnType.TEXT,
    "runtime_version": StateColumnType.TEXT,
    "entry_point": StateColumnType.TEXT,
    "body_sql_b64": StateColumnType.TEXT,
    "definition_text_b64": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
    "updated_at": StateColumnType.TIMESTAMP,
}

SEED_VERSION_COLUMNS: dict[str, StateColumnType] = {
    "seed_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
    "identity_metadata_hash": StateColumnType.TEXT,
    "identity_metadata_json_b64": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
    "updated_at": StateColumnType.TIMESTAMP,
}

PHYSICAL_RELATION_COLUMNS: dict[str, StateColumnType] = {
    "artifact_type": StateColumnType.TEXT,
    "artifact_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
    "database_name": StateColumnType.TEXT,
    "schema_name": StateColumnType.TEXT,
    "relation_name": StateColumnType.TEXT,
    "relation_type": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
    "updated_at": StateColumnType.TIMESTAMP,
}

PHYSICAL_RELATION_ANCESTRY_COLUMNS: dict[str, StateColumnType] = {
    "model_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
    "parent_model_name": StateColumnType.TEXT,
    "parent_version_hash": StateColumnType.TEXT,
    "seed_strategy": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
    "updated_at": StateColumnType.TIMESTAMP,
}

VIRTUAL_ENVIRONMENT_COLUMNS: dict[str, StateColumnType] = {
    "virtual_environment_name": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "baseline_virtual_environment_name": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
    "updated_at": StateColumnType.TIMESTAMP,
    "finalized_at": StateColumnType.TIMESTAMP,
}

VIRTUAL_ENVIRONMENT_MODEL_REF_COLUMNS: dict[str, StateColumnType] = {
    "virtual_environment_name": StateColumnType.TEXT,
    "model_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
    "updated_at": StateColumnType.TIMESTAMP,
}

VIRTUAL_ENVIRONMENT_FUNCTION_REF_COLUMNS: dict[str, StateColumnType] = {
    "virtual_environment_name": StateColumnType.TEXT,
    "function_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
    "updated_at": StateColumnType.TIMESTAMP,
}

VIRTUAL_ENVIRONMENT_SEED_REF_COLUMNS: dict[str, StateColumnType] = {
    "virtual_environment_name": StateColumnType.TEXT,
    "seed_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
    "updated_at": StateColumnType.TIMESTAMP,
}

SOURCE_FRESHNESS_OBSERVATION_COLUMNS: dict[str, StateColumnType] = {
    "virtual_environment_name": StateColumnType.TEXT,
    "source_name": StateColumnType.TEXT,
    "strategy": StateColumnType.TEXT,
    "value_kind": StateColumnType.TEXT,
    "data_version": StateColumnType.TEXT,
    "data_version_hash": StateColumnType.TEXT,
    "observed_at": StateColumnType.TIMESTAMP,
    "updated_at": StateColumnType.TIMESTAMP,
}

VIRTUAL_ENVIRONMENT_CHECKPOINT_COLUMNS: dict[str, StateColumnType] = {
    "checkpoint_id": StateColumnType.TEXT,
    "virtual_environment_name": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
}

VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_COLUMNS: dict[str, StateColumnType] = {
    "checkpoint_id": StateColumnType.TEXT,
    "model_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
}

VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_COLUMNS: dict[str, StateColumnType] = {
    "checkpoint_id": StateColumnType.TEXT,
    "function_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
}

VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_COLUMNS: dict[str, StateColumnType] = {
    "checkpoint_id": StateColumnType.TEXT,
    "seed_name": StateColumnType.TEXT,
    "version_hash": StateColumnType.TEXT,
}

LOCK_COLUMNS: dict[str, StateColumnType] = {
    "lock_key": StateColumnType.TEXT,
    "owner_id": StateColumnType.TEXT,
    "expires_at": StateColumnType.TIMESTAMP,
    "created_at": StateColumnType.TIMESTAMP,
    "updated_at": StateColumnType.TIMESTAMP,
}

STATE_OPERATION_COLUMNS: dict[str, StateColumnType] = {
    "operation_id": StateColumnType.TEXT,
    "operation_type": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "virtual_environment_name": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
    "updated_at": StateColumnType.TIMESTAMP,
}

PLAN_RUN_COLUMNS: dict[str, StateColumnType] = {
    "run_id": StateColumnType.TEXT,
    "command": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "virtual_environment_name": StateColumnType.TEXT,
    "started_at": StateColumnType.TIMESTAMP,
    "completed_at": StateColumnType.TIMESTAMP,
}

VIRTUAL_ENVIRONMENT_MODEL_REF_EVENT_COLUMNS: dict[str, StateColumnType] = {
    "event_id": StateColumnType.TEXT,
    "virtual_environment_name": StateColumnType.TEXT,
    "model_name": StateColumnType.TEXT,
    "previous_version_hash": StateColumnType.TEXT,
    "new_version_hash": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
}

RECONCILE_EVENT_COLUMNS: dict[str, StateColumnType] = {
    "event_id": StateColumnType.TEXT,
    "action": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "message": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
}

STATE_OPERATION_EVENT_COLUMNS: dict[str, StateColumnType] = {
    "event_id": StateColumnType.TEXT,
    "operation_id": StateColumnType.TEXT,
    "action": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "message": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
}

STATE_TABLE_COLUMNS: dict[str, dict[str, StateColumnType]] = {
    STATE_VERSION_TABLE: STATE_VERSION_COLUMNS,
    MODEL_VERSION_TABLE: MODEL_VERSION_COLUMNS,
    FUNCTION_VERSION_TABLE: FUNCTION_VERSION_COLUMNS,
    SEED_VERSION_TABLE: SEED_VERSION_COLUMNS,
    PHYSICAL_RELATION_TABLE: PHYSICAL_RELATION_COLUMNS,
    PHYSICAL_RELATION_ANCESTRY_TABLE: PHYSICAL_RELATION_ANCESTRY_COLUMNS,
    VIRTUAL_ENVIRONMENT_TABLE: VIRTUAL_ENVIRONMENT_COLUMNS,
    VIRTUAL_ENVIRONMENT_MODEL_REF_TABLE: VIRTUAL_ENVIRONMENT_MODEL_REF_COLUMNS,
    VIRTUAL_ENVIRONMENT_FUNCTION_REF_TABLE: VIRTUAL_ENVIRONMENT_FUNCTION_REF_COLUMNS,
    VIRTUAL_ENVIRONMENT_SEED_REF_TABLE: VIRTUAL_ENVIRONMENT_SEED_REF_COLUMNS,
    SOURCE_FRESHNESS_OBSERVATION_TABLE: SOURCE_FRESHNESS_OBSERVATION_COLUMNS,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE: VIRTUAL_ENVIRONMENT_CHECKPOINT_COLUMNS,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE: (
        VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_COLUMNS
    ),
    VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE: (
        VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_COLUMNS
    ),
    VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE: (
        VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_COLUMNS
    ),
    LOCK_TABLE: LOCK_COLUMNS,
    STATE_OPERATION_TABLE: STATE_OPERATION_COLUMNS,
    PLAN_RUN_TABLE: PLAN_RUN_COLUMNS,
    VIRTUAL_ENVIRONMENT_MODEL_REF_EVENT_TABLE: VIRTUAL_ENVIRONMENT_MODEL_REF_EVENT_COLUMNS,
    RECONCILE_EVENT_TABLE: RECONCILE_EVENT_COLUMNS,
    STATE_MIGRATION_EVENTS_TABLE: STATE_MIGRATION_EVENT_COLUMNS,
    STATE_OPERATION_EVENT_TABLE: STATE_OPERATION_EVENT_COLUMNS,
}

STATE_TABLE_INDEXES: dict[str, dict[str, tuple[str, ...]]] = {
    MODEL_VERSION_TABLE: {
        "idx_sqb_model_versions_identity": ("model_name", "version_hash"),
    },
    FUNCTION_VERSION_TABLE: {
        "idx_sqb_function_versions_identity": ("function_name", "version_hash"),
    },
    SEED_VERSION_TABLE: {
        "idx_sqb_seed_versions_identity": ("seed_name", "version_hash"),
    },
    PHYSICAL_RELATION_TABLE: {
        "idx_sqb_physical_relations_identity": (
            "artifact_type",
            "artifact_name",
            "version_hash",
        ),
    },
    PHYSICAL_RELATION_ANCESTRY_TABLE: {
        "idx_sqb_physical_relation_ancestry_identity": ("model_name", "version_hash"),
    },
    VIRTUAL_ENVIRONMENT_TABLE: {
        "idx_sqb_virtual_environments_identity": ("virtual_environment_name",),
    },
    VIRTUAL_ENVIRONMENT_MODEL_REF_TABLE: {
        "idx_sqb_virtual_environment_model_refs_identity": (
            "virtual_environment_name",
            "model_name",
        ),
    },
    VIRTUAL_ENVIRONMENT_FUNCTION_REF_TABLE: {
        "idx_sqb_virtual_environment_function_refs_identity": (
            "virtual_environment_name",
            "function_name",
        ),
    },
    VIRTUAL_ENVIRONMENT_SEED_REF_TABLE: {
        "idx_sqb_virtual_environment_seed_refs_identity": (
            "virtual_environment_name",
            "seed_name",
        ),
    },
    SOURCE_FRESHNESS_OBSERVATION_TABLE: {
        "idx_sqb_source_freshness_observations_identity": (
            "virtual_environment_name",
            "source_name",
        ),
    },
    VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE: {
        "idx_sqb_virtual_environment_checkpoints_identity": ("checkpoint_id",),
    },
    VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE: {
        "idx_sqb_virtual_environment_checkpoint_model_refs_identity": (
            "checkpoint_id",
            "model_name",
        ),
    },
    VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE: {
        "idx_sqb_virtual_environment_checkpoint_function_refs_identity": (
            "checkpoint_id",
            "function_name",
        ),
    },
    VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE: {
        "idx_sqb_virtual_environment_checkpoint_seed_refs_identity": (
            "checkpoint_id",
            "seed_name",
        ),
    },
    LOCK_TABLE: {
        "idx_sqb_locks_identity": ("lock_key",),
    },
    STATE_OPERATION_TABLE: {
        "idx_sqb_state_operations_identity": ("operation_id",),
    },
    PLAN_RUN_TABLE: {
        "idx_sqb_plan_runs_identity": ("run_id",),
    },
    VIRTUAL_ENVIRONMENT_MODEL_REF_EVENT_TABLE: {
        "idx_sqb_virtual_environment_model_ref_events_identity": ("event_id",),
    },
    RECONCILE_EVENT_TABLE: {
        "idx_sqb_reconcile_events_identity": ("event_id",),
    },
    STATE_MIGRATION_EVENTS_TABLE: {
        "idx_sqb_state_migration_events_identity": ("event_id",),
    },
    STATE_OPERATION_EVENT_TABLE: {
        "idx_sqb_state_operation_events_identity": ("event_id",),
    },
}
