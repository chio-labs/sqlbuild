"""Versioned state type declarations."""

from __future__ import annotations

from enum import StrEnum


class StateBackendName(StrEnum):
    DUCKDB = "duckdb"
    POSTGRES = "postgres"


class StateCommand(StrEnum):
    INIT = "init"
    MIGRATE = "migrate"
    ROLLBACK = "rollback"
    RESET = "reset"


class StateMigrationAction(StrEnum):
    INIT = "init"
    MIGRATE = "migrate"
    BACKUP = "backup"
    ROLLBACK = "rollback"
    RESET = "reset"


class StateMigrationStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class StateColumnType(StrEnum):
    INTEGER = "integer"
    TEXT = "text"
    TIMESTAMP = "timestamp"


class StateSchemaValidationIssueKind(StrEnum):
    MISSING_TABLE = "missing_table"
    MISSING_COLUMN = "missing_column"
    WRONG_TYPE = "wrong_type"
    MISSING_INDEX = "missing_index"


class ModelVersionStatus(StrEnum):
    PLANNED = "planned"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


class VirtualEnvironmentStatus(StrEnum):
    ACTIVE = "active"
    FINALIZING = "finalizing"
    FINALIZED = "finalized"
    FAILED = "failed"


class StateOperationStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
