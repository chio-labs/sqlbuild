"""Bulk fingerprint read operations."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError
from sqlbuild.compiler.fingerprints.main.shared.helpers.sql import (
    build_qualified_table_name,
    build_read_all_sql,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet


def read_latest_fingerprints(
    *,
    connection: Any,
    execute: Any,
    relation_exists: Callable[..., bool],
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    require_table: bool = False,
) -> FingerprintSet:
    """Read all fingerprints for a schema and resolve latest per node name in memory.

    Fingerprint table existence is checked via adapter metadata (`relation_exists`)
    rather than by swallowing probe-query errors, so operational failures propagate
    instead of being misread as "no fingerprint state".
    """

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    table_exists: bool = relation_exists(
        connection,
        database=database,
        schema=schema,
        name=FINGERPRINT_TABLE_NAME,
    )
    if not table_exists:
        if require_table:
            raise FingerprintInputError(f"Unable to read fingerprints from {qualified_name}")
        return FingerprintSet(schema=schema, fingerprints={})

    read_sql: str = build_read_all_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    try:
        result: Any = execute(connection, read_sql)
    except Exception as error:
        raise FingerprintInputError(
            f"Unable to read fingerprints from {qualified_name}. This can happen after "
            "upgrading from an older sqlbuild version; delete or rebuild the SQLBuild "
            "fingerprint table to regenerate fingerprints."
        ) from error
    rows: list[tuple[Any, ...]] = result.fetchall()
    latest: dict[str, Fingerprint] = {}
    row: tuple[Any, ...]
    for row in rows:
        fingerprint: Fingerprint = _row_to_fingerprint(row, qualified_name=qualified_name)
        node_name: str = fingerprint.node_name
        if node_name not in latest or fingerprint.ts > latest[node_name].ts:
            latest[node_name] = fingerprint
    return FingerprintSet(schema=schema, fingerprints=latest)


def _row_to_fingerprint(row: tuple[Any, ...], *, qualified_name: str) -> Fingerprint:
    raw_ts: Any = row[11]
    ts: datetime = raw_ts if isinstance(raw_ts, datetime) else datetime.fromisoformat(str(raw_ts))
    node_type: str = str(row[0])
    node_name: str = str(row[1])
    raw_target_database: Any = row[2]
    raw_target_schema: Any = row[3]
    raw_target_name: Any = row[4]
    definition_storage: str = str(row[9])
    metadata_json_storage: str = str(row[10])
    try:
        definition: str = base64.b64decode(
            definition_storage.encode("ascii"), validate=True
        ).decode("utf-8")
        metadata_json: str = base64.b64decode(
            metadata_json_storage.encode("ascii"), validate=True
        ).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise FingerprintInputError(
            f"Invalid fingerprint definition storage for '{node_name}' in {qualified_name}: "
            "expected base64-encoded UTF-8. This can happen after upgrading from an older "
            f"sqlbuild version; delete or rebuild {qualified_name} to regenerate fingerprints."
        ) from error
    return Fingerprint(
        node_type=node_type,
        node_name=node_name,
        target_database=str(raw_target_database) if raw_target_database is not None else None,
        target_schema=str(raw_target_schema) if raw_target_schema is not None else None,
        target_name=str(raw_target_name) if raw_target_name is not None else None,
        run_id=str(row[5]),
        definition_hash=str(row[6]),
        version_hash=str(row[7]),
        schema_fingerprint=str(row[8]),
        definition=definition,
        metadata_json=metadata_json,
        ts=ts,
    )
