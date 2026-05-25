"""State backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlbuild.versioned.state.models import StateSchemaValidationResult


class StateBackend(ABC):
    """State backend contract for versioned mode lifecycle operations."""

    @abstractmethod
    def connect(self, config: dict[str, object]) -> Any:
        """Open a state store connection."""
        ...

    @abstractmethod
    def close(self, connection: Any) -> None:
        """Close a state store connection."""
        ...

    @abstractmethod
    def initialize(self, connection: Any, *, schema: str, sqlbuild_version: str) -> None:
        """Create or migrate initial state schema objects."""
        ...

    @abstractmethod
    def validate_schema(self, connection: Any, *, schema: str) -> StateSchemaValidationResult:
        """Validate required state schema objects."""
        ...

    @abstractmethod
    def create_backup(self, connection: Any, *, schema: str) -> str:
        """Create a backup set and return its backup id."""
        ...

    @abstractmethod
    def rollback(self, connection: Any, *, schema: str, backup_id: str | None = None) -> str:
        """Restore state tables from a backup and return the used backup id."""
        ...

    @abstractmethod
    def reset(self, connection: Any, *, schema: str) -> None:
        """Drop state tables for the configured schema."""
        ...
