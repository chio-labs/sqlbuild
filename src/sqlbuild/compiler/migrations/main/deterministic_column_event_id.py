"""Build stable identifiers for immutable column migration events."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.compiler.migrations.models import MigrationRelation


def deterministic_column_migration_event_id(
    *,
    run_id: str,
    target_name: str | None,
    relation: MigrationRelation,
    origin_column: str,
    destination_column: str,
) -> str:
    """Return the content-addressed ID for one column rename performed by one run."""

    identity: tuple[object, ...] = (
        "column",
        run_id,
        target_name,
        relation.identity,
        origin_column.lower(),
        destination_column.lower(),
    )
    encoded: str = json.dumps(identity, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()
