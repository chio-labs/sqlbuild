"""Build stable identifiers for immutable model migration events."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.compiler.migrations.models import MigrationRelation


def deterministic_migration_event_id(
    *,
    run_id: str,
    target_name: str | None,
    origin: MigrationRelation,
    destination: MigrationRelation,
) -> str:
    """Return the content-addressed ID for one migration performed by one run."""

    identity: tuple[object, ...] = (
        run_id,
        target_name,
        origin.identity,
        destination.identity,
    )
    encoded: str = json.dumps(identity, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()
