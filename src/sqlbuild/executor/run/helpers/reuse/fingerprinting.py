"""Fingerprint write for model materialization lifecycle."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_MODEL
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.reuse.fingerprint_metadata import (
    model_fingerprint_metadata_with_audit_gate,
)
from sqlbuild.shared.helpers.identity.hashing import compute_query_hash


def try_write_fingerprint(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    query_change_tracking: bool,
    warnings: list[str],
    model_audits: tuple[AuditPlanEntry, ...] = (),
    audit_results: tuple[AuditExecutionResult, ...] = (),
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
        metadata_json: str = model_fingerprint_metadata_with_audit_gate(
            metadata_json=entry.fingerprint_metadata_json,
            model_audits=model_audits,
            audit_results=audit_results,
            run_id=run_id,
        )
        fingerprint: Fingerprint = Fingerprint(
            node_type=NODE_TYPE_MODEL,
            node_name=entry.name,
            target_database=entry.destination.database,
            target_schema=entry.destination.schema,
            target_name=entry.destination.name,
            run_id=run_id,
            definition_hash=compute_query_hash(entry.fingerprint_query_sql),
            version_hash=entry.fingerprint_version_hash
            or compute_query_hash(entry.fingerprint_query_sql),
            schema_fingerprint=schema_fp,
            definition=entry.fingerprint_query_sql,
            metadata_json=metadata_json,
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
            render_create_index_sqls=adapter.render_create_fingerprint_index_sqls,
        )
    except Exception as exc:
        warnings.append(
            f"fingerprint write failed for '{entry.name}'; "
            f"future query-change detection may be incorrect: {exc}"
        )
