"""Turn warehouse usage rows into relation reads."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from sqlbuild.adapter.contract._helpers.array_names import array_names
from sqlbuild.adapter.contract.models import RelationRead


def relation_reads(
    *, rows: Iterable[tuple[object, ...]], via_name: Callable[[str], str] = str
) -> tuple[RelationRead, ...]:
    """Reads from `(object, reader, queries, last read[, direct, via names])` rows."""

    reads: list[RelationRead] = []
    row: tuple[object, ...]
    for row in rows:
        direct_access, via_names = (*row[4:6], True, None)[:2]
        indirect: bool = not direct_access
        reads.append(
            RelationRead(
                object_name=str(row[0]),
                reader=None if row[1] is None else str(row[1]),
                query_count=int(str(row[2])),
                last_read_at=row[3],
                direct=not indirect,
                via=tuple(map(via_name, array_names(via_names))) if indirect else (),
            )
        )
    return tuple(reads)
