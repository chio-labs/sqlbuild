from __future__ import annotations

from typing import Any, ClassVar

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo

_NO_PROGRESS_ENV_VAR: str = "SQLBUILD_NO_PROGRESS"


def apply_no_progress_env(*, monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    """Set or clear the SQLBUILD_NO_PROGRESS env var for a status test."""

    if env_value is None:
        monkeypatch.delenv(_NO_PROGRESS_ENV_VAR, raising=False)
        return
    monkeypatch.setenv(_NO_PROGRESS_ENV_VAR, env_value)


class RecordingRelationAdapter(BaseAdapter):
    """Adapter double that records list_relations calls for relation-lookup tests."""

    adapter_name: ClassVar[str] = "recording_relation"

    def __init__(self, *, relations: tuple[RelationInfo, ...]) -> None:
        self._relations = relations
        self.list_relations_calls: list[tuple[str, ...]] = []

    def connect(self, config: dict[str, Any]) -> object:
        del config
        return object()

    def close(self, connection: Any) -> None:
        del connection

    def execute(self, connection: Any, sql: str) -> None:
        del connection, sql

    def list_relations(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        del connection, database, names
        self.list_relations_calls.append(tuple(schemas) if schemas is not None else ())
        requested: frozenset[str] | None = frozenset(schemas) if schemas is not None else None
        return tuple(
            relation
            for relation in self._relations
            if requested is None or relation.schema in requested
        )
