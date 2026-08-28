"""Bulk fingerprint read operations."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.fingerprints._helpers.sql import (
    build_qualified_table_name,
)
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_MODEL
from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet


def read_latest_fingerprints(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    table_exists: bool,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_read_latest_sql: Callable[..., str],
    require_table: bool = False,
    node_names: tuple[str, ...] | None = None,
    filtered_node_types: tuple[str, ...] = (),
) -> FingerprintSet:
    """Read the latest fingerprint per node identity from adapter-rendered SQL."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    if not table_exists:
        if require_table:
            raise FingerprintInputError(f"Unable to read fingerprints from {qualified_name}")
        return FingerprintSet(schema=schema, fingerprints={})

    read_sql: str = render_read_latest_sql(
        database=database,
        schema=schema,
    )
    if node_names is not None:
        if not node_names and not filtered_node_types:
            return FingerprintSet(schema=schema, fingerprints={})
        relevant_predicate: str = ""
        if node_names:
            literals: str = ", ".join(
                "'" + node_name.replace("'", "''") + "'" for node_name in node_names
            )
            relevant_predicate = f"node_name IN ({literals})"
        if filtered_node_types:
            type_literals: str = ", ".join(
                "'" + node_type.replace("'", "''") + "'"
                for node_type in filtered_node_types
            )
            python_identity_predicate: str = f"node_type NOT IN ({type_literals})"
            relevant_predicate = (
                f"{relevant_predicate} OR {python_identity_predicate}"
                if relevant_predicate
                else python_identity_predicate
            )
        read_sql = (
            f"SELECT * FROM ({read_sql}) AS __sqlbuild_relevant "
            f"WHERE {relevant_predicate}"
        )
    try:
        result: Any = execute(connection=connection, sql=read_sql)
    except Exception as error:
        raise FingerprintInputError(
            f"Unable to read fingerprints from {qualified_name}. This can happen after "
            "upgrading from an older sqlbuild version; delete or rebuild the SQLBuild "
            "fingerprint table to regenerate fingerprints."
        ) from error
    rows: list[tuple[Any, ...]] = result.fetchall()
    fingerprints: dict[str, Fingerprint] = {}
    fingerprints_by_identity: dict[tuple[str, str], Fingerprint] = {}
    row: tuple[Any, ...]
    for row in rows:
        fingerprint: Fingerprint = _row_to_fingerprint(row=row, qualified_name=qualified_name)
        fingerprints_by_identity[(fingerprint.node_type, fingerprint.node_name)] = fingerprint
        if fingerprint.node_type == NODE_TYPE_MODEL or fingerprint.node_name not in fingerprints:
            fingerprints[fingerprint.node_name] = fingerprint
    return FingerprintSet(
        schema=schema,
        fingerprints=fingerprints,
        fingerprints_by_identity=fingerprints_by_identity,
    )


def _row_to_fingerprint(*, row: tuple[Any, ...], qualified_name: str) -> Fingerprint:
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
