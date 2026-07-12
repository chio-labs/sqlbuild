"""Fingerprint writes for dbt node executions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.integrations.dbt.models import (
    DbtFingerprintDestination,
    DbtNodeExecutionResult,
)
from sqlbuild.integrations.dbt.types import DbtSupportedResourceType
from sqlbuild.shared.helpers.identity.hashing import compute_query_hash


def try_write_dbt_node_fingerprint(
    *,
    result: DbtNodeExecutionResult,
    adapter: BaseAdapter,
    connection: Any,
    destination: DbtFingerprintDestination,
    warnings: list[str],
    query_sql: str | None = None,
    seed_identity_hash: str | None = None,
    version_hash_override: str | None = None,
) -> list[str]:
    """Best-effort append of one successful dbt node fingerprint."""

    if not _is_successful_dbt_result(result):
        return warnings
    fingerprint_database: str | None = destination.fingerprint_database
    fingerprint_schema: str | None = destination.fingerprint_schema
    if fingerprint_schema is None:
        warnings.append(
            f"dbt fingerprint write skipped for '{result.unique_id}': fingerprint schema is missing"
        )
        return warnings
    try:
        metadata: str = json.dumps(
            {
                "unique_id": result.unique_id,
                "resource_type": result.resource_type,
                "node_checksum": result.node_checksum,
                "relation_name": result.relation_name,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if result.resource_type == DbtSupportedResourceType.MODEL:
            if query_sql is None:
                warnings.append(
                    f"dbt fingerprint write skipped for '{result.unique_id}': "
                    "dbt model SQL is missing"
                )
                return warnings
            definition: str = query_sql
        else:
            definition = metadata
        definition_hash: str = (
            seed_identity_hash
            if result.resource_type == DbtSupportedResourceType.SEED
            and seed_identity_hash is not None
            else result.node_checksum or compute_query_hash(definition)
        )
        version_hash: str = version_hash_override or definition_hash
        fingerprint: Fingerprint = Fingerprint(
            node_type=NODE_TYPE_DBT,
            node_name=result.unique_id,
            target_database=result.database,
            target_schema=result.schema,
            target_name=result.relation_name or result.node_name,
            run_id=destination.run_id,
            definition_hash=definition_hash,
            version_hash=version_hash,
            schema_fingerprint=hashlib.sha256(b"").hexdigest(),
            definition=definition,
            metadata_json=json.dumps(
                {
                    "resource_type": result.resource_type,
                    "node_name": result.node_name,
                    "materialized": result.materialized,
                    "status": result.status,
                    "target_name": destination.target_name,
                    "execution_time": result.execution_time,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            ts=datetime.now(tz=UTC),
        )
        adapter.ensure_schema(
            connection=connection,
            database=fingerprint_database,
            schema=fingerprint_schema,
            statement_recorder=StatementRecorder(),
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
    return warnings


def build_dbt_fingerprint_destination(project: CompiledProject) -> DbtFingerprintDestination:
    """Return the run-scoped fingerprint destination for a compiled dbt project."""

    return DbtFingerprintDestination(
        run_id=project.run_id,
        fingerprint_database=project.effective_target_database,
        fingerprint_schema=project.effective_target_schema,
        target_name=project.effective_target_name,
    )


def _is_successful_dbt_result(result: DbtNodeExecutionResult) -> bool:
    return result.status.lower() in {"ok", "success", "pass", "passed"}
