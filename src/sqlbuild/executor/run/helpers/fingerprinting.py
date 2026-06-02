"""Fingerprint write for model materialization lifecycle."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.shared.helpers.hashing import compute_ast_hash, compute_query_hash


def try_write_fingerprint(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    query_change_tracking: bool,
    warnings: list[str],
) -> None:
    """Attempt best-effort fingerprint write after successful lifecycle."""

    if not query_change_tracking:
        return
    target_schema: str | None = entry.destination.schema
    if target_schema is None:
        warnings.append(
            "fingerprint write skipped for "
            f"'{entry.name}': target schema is missing while query_change_tracking is enabled"
        )
        return
    try:
        schema_fp: str = hashlib.sha256(b"").hexdigest()
        fingerprint: Fingerprint = Fingerprint(
            model_name=entry.name,
            target_database=entry.destination.database,
            target_schema=entry.destination.schema,
            target_name=entry.destination.name,
            run_id=run_id,
            query_hash=compute_query_hash(entry.fingerprint_query_sql),
            ast_hash=compute_ast_hash(entry.fingerprint_query_sql),
            schema_fingerprint=schema_fp,
            query_sql=entry.fingerprint_query_sql,
            metadata_json=entry.fingerprint_metadata_json or "{}",
            ts=datetime.now(tz=UTC),
        )
        execute_fn: Any = adapter.execute
        write_fingerprint(
            connection=connection,
            execute=execute_fn,
            database=entry.destination.database,
            schema=target_schema,
            fingerprint=fingerprint,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_create_table_sql=adapter.render_create_fingerprint_table_sql,
        )
    except Exception as exc:
        warnings.append(
            f"fingerprint write failed for '{entry.name}'; "
            f"future query-change detection may be incorrect: {exc}"
        )
