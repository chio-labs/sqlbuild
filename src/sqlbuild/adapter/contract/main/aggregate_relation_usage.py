"""Fold per-reader reads into one usage per relation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from sqlbuild.adapter.contract._helpers.relation_reads import utc_datetime
from sqlbuild.adapter.contract.models import RelationInfo, RelationRead, RelationUsage
from sqlbuild.adapter.relations.constants import UNKNOWN_RELATION_READER


def aggregate_relation_usage(
    *, reads: Iterable[RelationRead], relations_by_name: Mapping[str, RelationInfo]
) -> tuple[RelationUsage, ...]:
    """One usage per read relation; it is direct when any reader read it directly."""

    readers: dict[str, dict[str, int]] = {}
    last_read: dict[str, datetime] = {}
    direct: set[str] = set()
    via: dict[str, set[str]] = {}
    read: RelationRead
    for read in reads:
        if read.object_name not in relations_by_name:
            continue
        reader: str = UNKNOWN_RELATION_READER if read.reader is None else read.reader
        counts: dict[str, int] = readers.setdefault(read.object_name, {})
        counts[reader] = counts.get(reader, 0) + read.query_count
        read_at: datetime = utc_datetime(read.last_read_at)
        last_read[read.object_name] = max(read_at, last_read.get(read.object_name, read_at))
        if read.direct:
            direct.add(read.object_name)
        via.setdefault(read.object_name, set()).update(read.via)
    usages: list[RelationUsage] = []
    object_name: str
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
                direct=object_name in direct,
                via=() if object_name in direct else tuple(sorted(via[object_name])),
            )
        )
    return tuple(usages)
