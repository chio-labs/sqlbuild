"""SQL generation helpers for fingerprint storage."""

from __future__ import annotations

from collections.abc import Callable

import sqlbuild._native as _native
from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError
from sqlbuild.compiler.fingerprints.models import Fingerprint


def build_qualified_table_name(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Build the fully qualified fingerprint table name for a target schema."""

    qualified_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=FINGERPRINT_TABLE_NAME,
    )
    if qualified_name is None:
        raise FingerprintInputError("fingerprint table requires a target schema")
    return qualified_name


def build_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
) -> str:
    """Build a CREATE TABLE IF NOT EXISTS statement for the fingerprint table."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    return _native.fingerprint_create_table_sql(
        qualified_name,
        (
            render_framework_type(FrameworkType.STRING),
            render_framework_type(FrameworkType.TIMESTAMP),
        ),
    )


def build_read_latest_sql(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    """Build a windowed SELECT for the latest fingerprint per node identity."""

    return _native.fingerprint_read_latest_sql(
        build_qualified_table_name(
            database=database,
            schema=schema,
            render_qualified_name=render_qualified_name,
        )
    )


def build_insert_sql(
    *,
    database: str | None,
    schema: str,
    fingerprint: Fingerprint,
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Build a complete INSERT statement for appending one fingerprint row."""

    return _native.fingerprint_insert_sql(
        build_qualified_table_name(
            database=database,
            schema=schema,
            render_qualified_name=render_qualified_name,
        ),
        fingerprint,
    )
