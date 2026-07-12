"""Janitor tracking-state helpers."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.executor.janitor.models import JanitorRelationKey
from sqlbuild.shared.helpers.diagnostics.logging import log_debug_event
from sqlbuild.shared.models import RelationLookup

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


def collect_tracked_relation_keys(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_schemas: set[tuple[str | None, str | None]],
) -> set[JanitorRelationKey]:
    """Collect exact physical relation keys from fingerprint metadata."""

    tracked_keys: set[JanitorRelationKey] = set()
    fingerprint_table_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            (database, schema, FINGERPRINT_TABLE_NAME)
            for database, schema in target_schemas
            if schema is not None
        ),
    )
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
                table_exists=fingerprint_table_lookup.exists(
                    database=database,
                    schema=schema,
                    name=FINGERPRINT_TABLE_NAME,
                ),
                database=database,
                schema=schema,
                render_qualified_name=adapter.render_qualified_name,
                render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
            )
        except Exception as error:
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message="janitor fingerprint tracking read failed; skipping schema",
                database=database,
                schema=schema,
                sqlbuild_error=str(error),
            )
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
