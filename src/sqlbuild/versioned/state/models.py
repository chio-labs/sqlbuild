"""Versioned state store models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.versioned.state.types import StateBackendName, StateSchemaValidationIssueKind


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
