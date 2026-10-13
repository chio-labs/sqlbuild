"""Bulk fingerprint read operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.fingerprints._helpers.sql import (
    build_qualified_table_name,
)
from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError
from sqlbuild.compiler.fingerprints.models import FingerprintSet


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
    relevant_sql: str | None = _native.fingerprint_relevant_read_sql(
        read_sql, node_names, filtered_node_types
    )
    if relevant_sql is None:
        return FingerprintSet(schema=schema, fingerprints={})
    try:
        result: Any = execute(connection=connection, sql=relevant_sql)
    except Exception as error:
        raise FingerprintInputError(
            f"Unable to read fingerprints from {qualified_name}. This can happen after "
            "upgrading from an older sqlbuild version; delete or rebuild the SQLBuild "
            "fingerprint table to regenerate fingerprints."
        ) from error
    rows: list[tuple[Any, ...]] = result.fetchall()
    return _native.fingerprint_set_from_rows(schema, qualified_name, rows)
