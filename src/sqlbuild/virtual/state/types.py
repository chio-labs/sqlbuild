"""Virtual state type declarations."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class StateTypeMatcher(Protocol):
    def __call__(self, *, actual_type: str, expected_type: StateColumnType) -> bool: ...


class StateBackendName(StrEnum):
    DUCKDB = "duckdb"
    POSTGRES = "postgres"


class StateCommand(StrEnum):
    INIT = "init"
    MIGRATE = "migrate"
    ROLLBACK = "rollback"
    RESET = "reset"
    ADOPT = "adopt"
    DETACH = "detach"


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


class PhysicalArtifactType(StrEnum):
    MODEL = "model"
    SEED = "seed"


class VirtualEnvironmentStatus(StrEnum):
    ACTIVE = "active"
    FINALIZING = "finalizing"
    FINALIZED = "finalized"
    DETACHED = "detached"
    FAILED = "failed"


class StateOperationStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StateOperationType(StrEnum):
    PROMOTE = "promote"
    ADOPT = "adopt"
    DETACH = "detach"


class ReconcileAction(StrEnum):
    REPORT = "report"
    REPAIR_VIEW = "repair_view"
    ATTACH = "attach"
