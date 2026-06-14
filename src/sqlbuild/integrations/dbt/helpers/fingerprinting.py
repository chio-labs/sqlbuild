"""Fingerprint writes for dbt node executions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.integrations.dbt.models import DbtNodeExecutionResult
from sqlbuild.shared.helpers.hashing import compute_query_hash


def try_write_dbt_node_fingerprint(
    *,
    result: DbtNodeExecutionResult,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    fingerprint_database: str | None,
    fingerprint_schema: str | None,
    target_name: str | None,
    warnings: list[str],
) -> None:
    """Best-effort append of one successful dbt node fingerprint."""

    if not _is_successful_dbt_result(result):
        return
    if fingerprint_schema is None:
        warnings.append(
            f"dbt fingerprint write skipped for '{result.unique_id}': fingerprint schema is missing"
        )
        return
    try:
        definition: str = json.dumps(
            {
                "unique_id": result.unique_id,
                "resource_type": result.resource_type,
                "node_checksum": result.node_checksum,
                "relation_name": result.relation_name,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        definition_hash: str = result.node_checksum or compute_query_hash(definition)
        fingerprint: Fingerprint = Fingerprint(
            node_type=NODE_TYPE_DBT,
            node_name=result.unique_id,
            target_database=result.database,
            target_schema=result.schema,
            target_name=result.relation_name or result.node_name,
            run_id=run_id,
            definition_hash=definition_hash,
            version_hash=definition_hash,
            schema_fingerprint=hashlib.sha256(b"").hexdigest(),
            definition=definition,
            metadata_json=json.dumps(
                {
                    "resource_type": result.resource_type,
                    "node_name": result.node_name,
                    "materialized": result.materialized,
                    "status": result.status,
                    "target_name": target_name,
                    "execution_time": result.execution_time,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            ts=datetime.now(tz=UTC),
        )
        execute_fn: Any = adapter.execute
        write_fingerprint(
            connection=connection,
            execute=execute_fn,
            database=fingerprint_database,
            schema=fingerprint_schema,
            fingerprint=fingerprint,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_create_table_sql=adapter.render_create_fingerprint_table_sql,
            render_create_index_sqls=adapter.render_create_fingerprint_index_sqls,
        )
    except Exception as exc:
        warnings.append(
            "dbt fingerprint write failed for "
            f"'{result.unique_id}'; future dbt change detection may be incorrect: {exc}"
        )


def _is_successful_dbt_result(result: DbtNodeExecutionResult) -> bool:
    return result.status.lower() in {"ok", "success", "pass", "passed"}
