"""Janitor tracking-state helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.executor.janitor.models import JanitorRelationKey


def collect_tracked_relation_keys(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_schemas: set[tuple[str | None, str | None]],
) -> set[JanitorRelationKey]:
    """Collect exact physical relation keys from fingerprint metadata."""

    tracked_keys: set[JanitorRelationKey] = set()
    schema_key: tuple[str | None, str | None]
    for schema_key in target_schemas:
        database: str | None = schema_key[0]
        schema: str | None = schema_key[1]
        if schema is None:
            continue
        try:
            fingerprint_set: FingerprintSet = read_latest_fingerprints(
                connection=connection,
                execute=adapter.execute,
                database=database,
                schema=schema,
            )
        except Exception:
            continue
        fingerprint: Fingerprint
        for fingerprint in fingerprint_set.fingerprints.values():
            if fingerprint.target_schema is None or fingerprint.target_name is None:
                continue
            tracked_keys.add(
                JanitorRelationKey(
                    database=fingerprint.target_database,
                    schema=fingerprint.target_schema,
                    name=fingerprint.target_name,
                )
            )
    return tracked_keys
