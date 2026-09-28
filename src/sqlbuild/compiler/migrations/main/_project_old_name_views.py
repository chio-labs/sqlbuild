"""Project old-name view histories from recorded moves and old-name facts."""

from __future__ import annotations

from collections.abc import Iterable

from sqlbuild.compiler.migrations.models import (
    MigrationEvent,
    OldNameViewEvent,
    OldNameViewHistory,
)
from sqlbuild.compiler.migrations.types import OldNameViewEventType


def project_old_name_views(
    *, moves: Iterable[MigrationEvent], facts: Iterable[OldNameViewEvent]
) -> tuple[OldNameViewHistory, ...]:
    """Return one history per recorded move whose old name needs a compatibility view."""

    by_move: dict[str, dict[OldNameViewEventType, OldNameViewEvent]] = {}
    fact: OldNameViewEvent
    for fact in sorted(facts, key=lambda item: (item.created_at, item.event_id)):
        _ = by_move.setdefault(fact.migration_event_id, {}).setdefault(fact.event_type, fact)
    histories: list[OldNameViewHistory] = []
    move: MigrationEvent
    for move in sorted(moves, key=lambda item: (item.created_at, item.event_id)):
        recorded: dict[OldNameViewEventType, OldNameViewEvent] = by_move.get(move.event_id, {})
        required: OldNameViewEvent | None = recorded.get(OldNameViewEventType.REQUIRED)
        if required is None:
            continue
        histories.append(
            OldNameViewHistory(
                move=move,
                required=required,
                archived=recorded.get(OldNameViewEventType.ORIGIN_ARCHIVED),
                created=recorded.get(OldNameViewEventType.VIEW_CREATED),
                dropped=recorded.get(OldNameViewEventType.VIEW_DROPPED),
            )
        )
    return tuple(histories)
