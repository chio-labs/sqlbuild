"""Deterministic janitor audit event identity helpers."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.executor.janitor_events.types import JanitorEventType


def build_janitor_event_id_impl(
    *,
    event_type: JanitorEventType,
    run_id: str,
    relation_database: str | None,
    relation_schema: str,
    archive_name: str,
) -> str:
    """Return the content-addressed ID for one janitor action within one run."""

    identity: tuple[object, ...] = (
        event_type.value,
        run_id,
        relation_database,
        relation_schema,
        archive_name,
    )
    encoded: str = json.dumps(identity, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
