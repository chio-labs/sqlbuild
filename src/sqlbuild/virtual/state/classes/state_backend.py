"""State backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationRecord,
    StateLockRecord,
    StateSchemaValidationResult,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)


class StateBackend(ABC):
    """State backend contract for virtual mode lifecycle operations."""

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

    @abstractmethod
    def upsert_model_version(
        self, connection: Any, *, schema: str, record: ModelVersionRecord
    ) -> None:
        """Insert or replace a model version row."""
        ...

    @abstractmethod
    def get_model_version(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> ModelVersionRecord | None:
        """Return a model version row if it exists."""
        ...

    @abstractmethod
    def upsert_physical_relation(
        self, connection: Any, *, schema: str, record: PhysicalRelationRecord
    ) -> None:
        """Insert or replace a physical relation row."""
        ...

    @abstractmethod
    def get_physical_relation(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationRecord | None:
        """Return a physical relation row if it exists."""
        ...

    @abstractmethod
    def upsert_virtual_environment(
        self, connection: Any, *, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        """Insert or replace a virtual environment row."""
        ...

    @abstractmethod
    def get_virtual_environment(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> VirtualEnvironmentRecord | None:
        """Return a virtual environment row if it exists."""
        ...

    @abstractmethod
    def replace_virtual_environment_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentRefRecord, ...],
    ) -> None:
        """Replace all refs for a virtual environment."""
        ...

    @abstractmethod
    def get_virtual_environment_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentRefRecord, ...]:
        """Return refs for a virtual environment."""
        ...

    @abstractmethod
    def acquire_lock(
        self,
        connection: Any,
        *,
        schema: str,
        lock_key: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        """Acquire or replace an expired lock."""
        ...

    @abstractmethod
    def release_lock(self, connection: Any, *, schema: str, lock_key: str, owner_id: str) -> bool:
        """Release a lock owned by the given owner."""
        ...

    @abstractmethod
    def list_active_locks(self, connection: Any, *, schema: str) -> tuple[StateLockRecord, ...]:
        """Return non-expired locks."""
        ...
