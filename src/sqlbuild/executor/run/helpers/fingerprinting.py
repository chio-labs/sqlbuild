"""Fingerprint write for model materialization lifecycle."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import ModelPlanEntry


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
    target_schema: str | None = entry.target.schema
    if target_schema is None:
        warnings.append(
            "fingerprint write skipped for "
            f"'{entry.name}': target schema is missing while query_change_tracking is enabled"
        )
        return
    try:
        normalized_sql: str = " ".join(entry.fingerprint_query_sql.split())
        query_hash: str = hashlib.sha256(normalized_sql.encode()).hexdigest()
        schema_fp: str = hashlib.sha256(b"").hexdigest()
        fingerprint: Fingerprint = Fingerprint(
            model_name=entry.name,
            target_database=entry.target.database,
            target_schema=entry.target.schema,
            target_name=entry.target.name,
            run_id=run_id,
            query_hash=query_hash,
            ast_hash=None,
            schema_fingerprint=schema_fp,
            query_sql=entry.fingerprint_query_sql,
            ts=datetime.now(tz=UTC),
        )
        execute_fn: Any = adapter.execute
        write_fingerprint(
            connection=connection,
            execute=execute_fn,
            database=entry.target.database,
            schema=target_schema,
            fingerprint=fingerprint,
        )
    except Exception as exc:
        warnings.append(
            f"fingerprint write failed for '{entry.name}'; "
            f"future query-change detection may be incorrect: {exc}"
        )
