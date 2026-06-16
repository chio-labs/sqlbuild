"""dbt reuse_from execution helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.executor.run.main.promote import promote_run_relation_to_destination
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import DbtInteropPlan, DbtReusePlanEntry
from sqlbuild.integrations.dbt.types import DbtReusePlanAction


def execute_dbt_complete_reuse_plan(
    *,
    adapter: BaseAdapter,
    connection: Any,
    manifest: DbtManifestIndex,
    plan: DbtInteropPlan,
    run_id: str,
    fingerprint_database: str | None,
    fingerprint_schema: str | None,
    target_name: str | None,
    warnings: list[str],
) -> tuple[str, ...]:
    """Execute complete table reuse entries and return reused dbt unique IDs."""

    if plan.dbt_reuse_plan is None:
        return ()
    reused_unique_ids: list[str] = []
    entry: DbtReusePlanEntry
    for entry in plan.dbt_reuse_plan.entries:
        if entry.action != DbtReusePlanAction.COMPLETE_REUSE:
            continue
        if entry.destination_relation_name is None or entry.origin_relation_name is None:
            continue
        model: DbtManifestModel | None = manifest.models_by_unique_id.get(entry.unique_id)
        if model is None:
            continue
        _execute_complete_reuse_entry(
            adapter=adapter,
            connection=connection,
            entry=entry,
            model=model,
            run_id=run_id,
            fingerprint_database=fingerprint_database,
            fingerprint_schema=fingerprint_schema,
            target_name=target_name,
            warnings=warnings,
        )
        reused_unique_ids.append(entry.unique_id)
    return tuple(reused_unique_ids)


def _execute_complete_reuse_entry(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: DbtReusePlanEntry,
    model: DbtManifestModel,
    run_id: str,
    fingerprint_database: str | None,
    fingerprint_schema: str | None,
    target_name: str | None,
    warnings: list[str],
) -> None:
    destination_database, destination_schema, destination_name = _relation_parts(
        relation_name=entry.destination_relation_name or model.relation_name
    )
    staging_relation: str = _staging_relation_name(
        database=destination_database,
        schema=destination_schema,
        name=destination_name,
    )
    recorder: StatementRecorder = StatementRecorder()
    adapter.ensure_schema(
        connection,
        database=destination_database,
        schema=destination_schema,
        statement_recorder=recorder,
    )
    adapter.drop(
        connection, destination=staging_relation, if_exists=True, statement_recorder=recorder
    )
    adapter.create_table_as(
        connection,
        destination=staging_relation,
        sql=f"SELECT * FROM {entry.origin_relation_name}",
        statement_recorder=recorder,
    )
    promote_run_relation_to_destination(
        adapter=adapter,
        connection=connection,
        origin_relation=staging_relation,
        destination_relation=entry.destination_relation_name or model.relation_name,
        destination_database=destination_database,
        destination_schema=destination_schema,
        destination_name=destination_name,
        statement_recorder=recorder,
    )
    _write_reuse_fingerprint(
        adapter=adapter,
        connection=connection,
        entry=entry,
        model=model,
        run_id=run_id,
        fingerprint_database=fingerprint_database,
        fingerprint_schema=fingerprint_schema,
        target_name=target_name,
        warnings=warnings,
    )


def _write_reuse_fingerprint(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: DbtReusePlanEntry,
    model: DbtManifestModel,
    run_id: str,
    fingerprint_database: str | None,
    fingerprint_schema: str | None,
    target_name: str | None,
    warnings: list[str],
) -> None:
    if fingerprint_schema is None:
        warnings.append(
            f"dbt reuse fingerprint write skipped for '{entry.unique_id}': "
            "fingerprint schema is missing"
        )
        return
    definition_hash: str = (
        model.node_checksum or hashlib.sha256(model.query_sql.encode("utf-8")).hexdigest()
    )
    target_database, target_schema, destination_relation_name = _relation_parts(
        relation_name=entry.destination_relation_name or model.relation_name
    )
    fingerprint: Fingerprint = Fingerprint(
        node_type=NODE_TYPE_DBT,
        node_name=entry.unique_id,
        target_database=target_database,
        target_schema=target_schema,
        target_name=destination_relation_name,
        run_id=run_id,
        definition_hash=definition_hash,
        version_hash=definition_hash,
        schema_fingerprint=hashlib.sha256(b"").hexdigest(),
        definition=model.query_sql,
        metadata_json=json.dumps(
            {
                "materialization_mode": "reuse_clone",
                "reuse_mode": "complete",
                "origin_relation": entry.origin_relation_name,
                "destination_relation": entry.destination_relation_name,
                "materialization": entry.materialization,
                "dbt_target_name": target_name,
                "status": "success",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        ts=datetime.now(tz=UTC),
    )
    write_fingerprint(
        connection=connection,
        execute=adapter.execute,
        database=fingerprint_database,
        schema=fingerprint_schema,
        fingerprint=fingerprint,
        render_qualified_name=adapter.render_qualified_name,
        render_framework_type=adapter.render_framework_type,
        render_create_table_sql=adapter.render_create_fingerprint_table_sql,
        render_create_index_sqls=adapter.render_create_fingerprint_index_sqls,
    )


def _relation_parts(*, relation_name: str) -> tuple[str | None, str | None, str]:
    parts: list[str] = [part.strip('"') for part in relation_name.split(".")]
    if len(parts) >= 3:
        return parts[-3], parts[-2], parts[-1]
    if len(parts) == 2:
        return None, parts[0], parts[1]
    return None, None, parts[0]


def _staging_relation_name(*, database: str | None, schema: str | None, name: str) -> str:
    staging_name: str = f"{name}__sqlbuild_reuse_stage"
    if database is not None and schema is not None:
        return f"{database}.{schema}.{staging_name}"
    if schema is not None:
        return f"{schema}.{staging_name}"
    return staging_name
