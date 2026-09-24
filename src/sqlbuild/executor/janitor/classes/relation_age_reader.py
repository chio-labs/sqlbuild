"""Candidate-scoped relation age metadata reader for janitor planning."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo


class JanitorRelationAgeReader:
    """Adapter connection used to read age metadata for janitor candidates only."""

    def __init__(self, *, adapter: BaseAdapter, connection: Any) -> None:
        self.adapter: BaseAdapter = adapter
        self.connection: Any = connection

    def supported(self) -> bool:
        """Return whether the adapter reports reliable relation age metadata."""

        return self.adapter.supports_relation_age_metadata()

    def read(self, relations: tuple[RelationInfo, ...]) -> tuple[RelationInfo, ...]:
        """Return candidate relations with age timestamps filled when supported."""

        if not relations or not self.supported():
            return relations
        return self.adapter.with_relation_age_metadata(
            connection=self.connection, relations=relations
        )
