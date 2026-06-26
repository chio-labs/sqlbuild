"""Clone execution models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import LifeCycleEvent, RelationInfo
from sqlbuild.executor.clone.types import CloneAction, CloneStatus


@dataclass(frozen=True)
class CloneOriginSnapshot:
    """Indexed origin relations gathered once, answering existence and transient-ness."""

    relations_by_key: dict[tuple[str | None, str], RelationInfo] = field(default_factory=dict)

    @staticmethod
    def key(*, schema: str | None, name: str) -> tuple[str | None, str]:
        """Build the case-insensitive lookup key for one origin relation."""

        return (None if schema is None else schema.lower(), name.lower())

    def exists(self, *, schema: str | None, name: str) -> bool:
        """Return whether the origin relation was present in the gathered snapshot."""

        return self.key(schema=schema, name=name) in self.relations_by_key

    def is_transient(self, *, schema: str | None, name: str) -> bool:
        """Return whether the origin relation is transient, defaulting to False."""

        relation: RelationInfo | None = self.relations_by_key.get(
            self.key(schema=schema, name=name)
        )
        if relation is None:
            return False
        return bool(relation.is_transient)


@dataclass(frozen=True)
class CloneItemResult:
    name: str
    action: CloneAction
    status: CloneStatus
    message: str | None = None
    origin_relation: str | None = None
    destination_relation: str | None = None
    duration_seconds: float | None = None
    executed_statements: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CloneExecutionResult:
    item_results: tuple[CloneItemResult, ...] = field(default_factory=tuple)
