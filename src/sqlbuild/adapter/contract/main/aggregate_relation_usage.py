"""Fold per-reader usage rows into one usage per relation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsage
from sqlbuild.adapter.relations.constants import UNKNOWN_RELATION_READER


def aggregate_relation_usage(
    *, rows: Iterable[tuple[object, ...]], relations_by_name: Mapping[str, RelationInfo]
) -> tuple[RelationUsage, ...]:
    """One usage per read relation from `(object_name, reader, query_count, last_read)` rows."""

    readers: dict[str, dict[str, int]] = {}
    last_read: dict[str, datetime] = {}
    row: tuple[object, ...]
    for row in rows:
        object_name: str = str(row[0])
        if object_name not in relations_by_name:
            continue
        reader: str = UNKNOWN_RELATION_READER if row[1] is None else str(row[1])
        counts: dict[str, int] = readers.setdefault(object_name, {})
        counts[reader] = counts.get(reader, 0) + int(str(row[2]))
        read_at: datetime = _utc(row[3])
        last_read[object_name] = max(read_at, last_read.get(object_name, read_at))
    usages: list[RelationUsage] = []
    for object_name in sorted(readers):
        relation: RelationInfo = relations_by_name[object_name]
        counts = readers[object_name]
        usages.append(
            RelationUsage(
                database=relation.database,
                schema=relation.schema,
                name=relation.name,
                last_read_at=last_read[object_name],
                readers=tuple(sorted(counts, key=lambda reader: (-counts[reader], reader))),
                query_count=sum(counts.values()),
            )
        )
    return tuple(usages)


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
