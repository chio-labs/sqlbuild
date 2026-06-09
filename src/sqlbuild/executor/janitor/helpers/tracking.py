"""Janitor tracking-state helpers."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.executor.janitor.models import JanitorRelationKey
from sqlbuild.shared.helpers.diagnostics_logging import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


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
                relation_exists=adapter.relation_exists,
                database=database,
                schema=schema,
                render_qualified_name=adapter.render_qualified_name,
            )
        except Exception as error:
            log_debug_event(
                _DEBUG_LOGGER,
                "janitor fingerprint tracking read failed; skipping schema",
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
