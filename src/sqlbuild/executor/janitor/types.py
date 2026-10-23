"""Janitor execution types."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild.executor.janitor.models import JanitorProgressItem


class JanitorPhase(StrEnum):
    DELETE_RELATIONS = "delete_relations"
    ARCHIVE = "archive"
    DELETE_ARCHIVES = "delete_archives"
    DROP_OLD_NAME_VIEWS = "drop_old_name_views"
    DROP_QUERY_ARTIFACTS = "drop_query_artifacts"
    DROP_REVIEW_SCHEMAS = "drop_review_schemas"
    PRUNE_DIRECT_STATE = "prune_direct_state"


class JanitorAction(StrEnum):
    ARCHIVED = "archived"
    DELETED = "deleted"
    DROPPED = "dropped"
    RECORDED = "recorded"
    PRUNED = "pruned"


class JanitorProgress(Protocol):
    def phase_started(self, *, phase: str, total: int) -> None: ...

    def item_finished(self, *, phase: str, item: JanitorProgressItem) -> None: ...

    def phase_finished(self, *, phase: str, failed: bool) -> None: ...

    def events_unwritten(self, *, count: int, schemas: tuple[str, ...], error: str) -> None: ...


class JanitorConnectionProgress(Protocol):
    def on_connection_start(self, connection_count: int) -> None: ...

    def on_connection_complete(self, *, connection_count: int, elapsed_seconds: float) -> None: ...

    def on_connection_error(self, *, connection_count: int, elapsed_seconds: float) -> None: ...
