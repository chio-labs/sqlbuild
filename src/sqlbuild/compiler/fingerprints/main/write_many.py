"""Batched fingerprint write entrypoint."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute, FrameworkType
from sqlbuild.compiler.fingerprints._helpers.write_many import write_fingerprints_impl
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.fingerprints.types import FingerprintWriteProgress


def write_fingerprints(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    fingerprints: Sequence[Fingerprint],
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    render_create_table_sql: Callable[..., str] | None = None,
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None = None,
    on_progress: FingerprintWriteProgress | None = None,
) -> None:
    """Append fingerprints using one table setup and bounded multi-row inserts."""

    _ = write_fingerprints_impl(
        connection=connection,
        execute=execute,
        database=database,
        schema=schema,
        fingerprints=fingerprints,
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
        render_create_table_sql=render_create_table_sql,
        render_create_index_sqls=render_create_index_sqls,
        on_progress=on_progress,
    )
