"""Helpers for relation metadata cache tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.relations.classes.relation_metadata_cache import RelationMetadataCache
from sqlbuild.adapter.relations.constants import RELATION_COLUMNS_LOOKUP


@dataclass
class CountingColumnsRead:
    """Column read double that counts calls and can run a statement while reading."""

    cache: RelationMetadataCache
    statement_during_read: str | None = None
    reads: int = 0
    columns: tuple[ColumnInfo, ...] = field(
        default_factory=lambda: (ColumnInfo(name="order_id", type="NUMBER(38,0)"),)
    )

    def __call__(self) -> tuple[ColumnInfo, ...]:
        self.reads += 1
        statements: tuple[str, ...] = tuple(filter(None, (self.statement_during_read,)))
        statement: str
        for statement in statements:
            self.cache.observe_statement(sql=statement)
        return self.columns


def read_orders(*, cache: RelationMetadataCache, read: CountingColumnsRead) -> None:
    """Look up the ``orders`` columns once through the cache."""

    _ = cache.lookup(
        kind=RELATION_COLUMNS_LOOKUP, database="analytics", schema="marts", name="orders", read=read
    )
