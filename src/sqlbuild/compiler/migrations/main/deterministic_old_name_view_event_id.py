"""Build stable identifiers for immutable old-name view facts."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.compiler.migrations.types import OldNameViewEventType


def deterministic_old_name_view_event_id(
    *, event_type: OldNameViewEventType, migration_event_id: str
) -> str:
    """Return the content-addressed ID of one old-name step of one recorded move."""

    identity: tuple[object, ...] = ("old_name", event_type.value, migration_event_id)
    encoded: str = json.dumps(identity, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()
