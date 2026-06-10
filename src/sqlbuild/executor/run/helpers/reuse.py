"""Relation reuse materialization helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import FingerprintSet
from sqlbuild.compiler.planner.models import RelationReusePlan
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.shared.helpers.naming import resolve_relation_location_qualified_name


def create_relation_from_reuse_origin(
    *,
    adapter: BaseAdapter,
    connection: Any,
    origin_relation: str,
    destination_relation: str,
    hard_copy: bool,
    statement_recorder: StatementRecorder,
) -> None:
    """Create a destination relation from the configured reuse origin relation."""

    if hard_copy:
        adapter.durable_clone(
            connection,
            origin=origin_relation,
            destination=destination_relation,
            statement_recorder=statement_recorder,
        )
        return
    if not adapter.supports_zero_copy_clone():
        raise ExecutorInputError(
            f"adapter '{adapter.adapter_name}' does not support cheap relation reuse. "
            "Set reuse_hard_copy = true for this target to force copy-based reuse, "
            "or remove reuse_from to build normally."
        )
    adapter.clone(
        connection,
        origin=origin_relation,
        destination=destination_relation,
        hard_copy=False,
        statement_recorder=statement_recorder,
    )


def create_relation_from_reuse_plan(
    *,
    adapter: BaseAdapter,
    connection: Any,
    model_name: str,
    expected_version_hash: str | None,
    relation_reuse: RelationReusePlan,
    destination_relation: str,
    statement_recorder: StatementRecorder,
) -> None:
    """Validate and create a concrete destination relation from a reuse plan."""

    validate_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        model_name=model_name,
        expected_version_hash=expected_version_hash,
        reuse_from_target_name=relation_reuse.reuse_from_target_name,
        reuse_origin_fingerprint_database=relation_reuse.fingerprint_database,
        reuse_origin_fingerprint_schema=relation_reuse.fingerprint_schema,
    )
    create_relation_from_reuse_origin(
        adapter=adapter,
        connection=connection,
        origin_relation=resolve_relation_location_qualified_name(
            adapter=adapter,
            location=relation_reuse.origin,
        ),
        destination_relation=destination_relation,
        hard_copy=relation_reuse.hard_copy,
        statement_recorder=statement_recorder,
    )


def validate_reuse_origin_fingerprint(
    *,
    adapter: BaseAdapter,
    connection: Any,
    model_name: str,
    expected_version_hash: str | None,
    reuse_from_target_name: str | None,
    reuse_origin_fingerprint_database: str | None,
    reuse_origin_fingerprint_schema: str | None,
) -> None:
    """Recheck reuse_from target fingerprint immediately before relation reuse."""

    if expected_version_hash is None:
        raise ExecutorInputError(
            f"model '{model_name}' cannot reuse a relation because its expected version hash "
            "is unavailable. Rerun planning and try again."
        )
    if reuse_origin_fingerprint_schema is None:
        raise ExecutorInputError(
            f"model '{model_name}' cannot reuse from target '{reuse_from_target_name}' because "
            "the reuse origin fingerprint schema is unavailable. Rerun planning and try again."
        )
    fingerprint_set: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=adapter.execute,
        relation_exists=adapter.relation_exists,
        database=reuse_origin_fingerprint_database,
        schema=reuse_origin_fingerprint_schema,
        render_qualified_name=adapter.render_qualified_name,
        require_table=True,
    )
    reuse_origin_version_hash: str | None = (
        fingerprint_set.fingerprints[model_name].version_hash
        if model_name in fingerprint_set.fingerprints
        else None
    )
    if reuse_origin_version_hash != expected_version_hash:
        raise ExecutorInputError(
            f"model '{model_name}' cannot reuse from target '{reuse_from_target_name}' because "
            "the reuse origin fingerprint changed after planning. Rerun the plan and try again."
        )
