"""Versioned state store models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.versioned.state.types import (
    ModelVersionStatus,
    StateBackendName,
    StateSchemaValidationIssueKind,
    VirtualEnvironmentStatus,
)


@dataclass(frozen=True)
class StateBackendConfig:
    """Resolved state backend configuration."""

    backend: StateBackendName
    schema: str
    connection: dict[str, object]
    allow_reset: bool = False


@dataclass(frozen=True)
class StateSchemaValidationIssue:
    """One state schema validation issue."""

    kind: StateSchemaValidationIssueKind
    table_name: str
    message: str
    column_name: str | None = None


@dataclass(frozen=True)
class StateSchemaValidationResult:
    """State schema validation result."""

    issues: tuple[StateSchemaValidationIssue, ...] = field(default_factory=tuple)

    @property
    def valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class ModelVersionRecord:
    """Current state row for one model version."""

    model_name: str
    version_hash: str
    data_hash: str
    metadata_hash: str
    status: ModelVersionStatus


@dataclass(frozen=True)
class PhysicalRelationRecord:
    """Current state row for a physical relation that stores one model version."""

    model_name: str
    version_hash: str
    database_name: str | None
    schema_name: str
    relation_name: str
    relation_type: str


@dataclass(frozen=True)
class VirtualEnvironmentRecord:
    """Current state row for one virtual data environment."""

    virtual_environment_name: str
    status: VirtualEnvironmentStatus
    baseline_virtual_environment_name: str | None = None
    finalized_at: datetime | None = None


@dataclass(frozen=True)
class VirtualEnvironmentRefRecord:
    """Current state row mapping a VDE model ref to a model version."""

    virtual_environment_name: str
    model_name: str
    version_hash: str


@dataclass(frozen=True)
class StateLockRecord:
    """Current state row for one active lock."""

    lock_key: str
    owner_id: str
    expires_at: datetime


@dataclass(frozen=True)
class StateLockLease:
    """Acquired state lock lease."""

    lock_key: str
    owner_id: str
    expires_at: datetime
