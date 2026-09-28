"""Cache-state changes applied between planner runs in migration fingerprint cache tests."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path

import pytest

import sqlbuild.compiler.planner.classes.migration_fingerprint_cache as fingerprint_cache
from sqlbuild.compiler.planner._helpers.migrations.fingerprint import build_migration_fingerprint

ORDERS_SQL: str = 'SELECT o.order_id, o.amount_cents FROM __ref("stg_orders") AS o'
CURSOR_METADATA: str = json.dumps(
    {
        "model_name": "daily_orders",
        "config": {"materialized": "incremental", "cursor_inputs": {"order_events": "event_date"}},
    }
)
PLAIN_METADATA: str = json.dumps(
    {"model_name": "daily_orders", "config": {"materialized": "table"}}
)
DATABASE_GLOB: str = "migration-fingerprints-v*/migration-fingerprints.sqlite3"


def count_fingerprint_computations(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count every fingerprint computed instead of reused."""

    computations: list[int] = []

    def counting(
        *,
        query_sql: str,
        metadata_json: str,
        ref_identities: Mapping[str, str],
        dialect: str | None,
    ) -> str | None:
        computations.append(1)
        return build_migration_fingerprint(
            query_sql=query_sql,
            metadata_json=metadata_json,
            ref_identities=ref_identities,
            dialect=dialect,
        )

    monkeypatch.setattr(fingerprint_cache, "build_migration_fingerprint", counting)
    return computations


def keep_cache(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave the persisted cache untouched."""

    del root, monkeypatch


def corrupt_database(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Overwrite the cache database with bytes that are not SQLite."""

    del monkeypatch
    next(root.glob(DATABASE_GLOB)).write_bytes(b"not a database")


def tamper_entries(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Change every stored fingerprint without updating its digest."""

    del monkeypatch
    connection: sqlite3.Connection = sqlite3.connect(next(root.glob(DATABASE_GLOB)))
    try:
        _ = connection.execute(
            'UPDATE migration_fingerprint SET payload = replace(payload, \'"f":"\', \'"f":"0\')'
        )
        connection.commit()
    finally:
        connection.close()


def upgrade_sqlbuild(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Report a different installed sqlbuild version for the next run."""

    del root
    monkeypatch.setattr(fingerprint_cache, "_package_version", lambda package: f"{package}-next")
