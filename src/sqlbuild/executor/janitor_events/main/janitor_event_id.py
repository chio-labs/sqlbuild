"""Janitor audit event identity entrypoint."""

from __future__ import annotations

from sqlbuild.executor.janitor_events._helpers.identity import build_janitor_event_id_impl
from sqlbuild.executor.janitor_events.types import JanitorEventType


def build_janitor_event_id(
    *,
    event_type: JanitorEventType,
    run_id: str,
    relation_database: str | None,
    relation_schema: str,
    archive_name: str,
) -> str:
    """Return the deterministic ID for one janitor action within one run."""

    return build_janitor_event_id_impl(
        event_type=event_type,
        run_id=run_id,
        relation_database=relation_database,
        relation_schema=relation_schema,
        archive_name=archive_name,
    )
