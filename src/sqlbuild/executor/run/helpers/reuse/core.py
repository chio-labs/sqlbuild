"""Relation reuse materialization helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.main.operations.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.planner.models import RelationReusePlan
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.shared.helpers.identity.naming import resolve_relation_location_qualified_name


def _origin_is_transient(
    *, adapter: BaseAdapter, connection: Any, location: CompiledRelationLocation
) -> bool:
    """Return whether the reuse origin warehouse relation is transient, defaulting to False."""

    if location.schema is None:
        return False
    relations: tuple[Any, ...] = adapter.list_relations(
        connection,
        database=location.database,
        schemas=(location.schema,),
        names=(location.name,),
    )
    target_name: str = location.name.lower()
    for relation in relations:
        if relation.name == target_name:
            return bool(relation.is_transient)
    return False


def create_relation_from_reuse_origin(
    *,
    adapter: BaseAdapter,
    connection: Any,
    origin_relation: str,
    destination_relation: str,
    hard_copy: bool,
    statement_recorder: StatementRecorder,
    origin_is_transient: bool = False,
    destination_target_name: str | None = None,
    reuse_from_target_name: str | None = None,
) -> None:
    """Create a destination relation from the configured reuse origin relation."""

    if hard_copy:
        adapter.create_table_as(
            connection,
            destination=destination_relation,
            sql=f"SELECT * FROM {origin_relation}",
            statement_recorder=statement_recorder,
        )
        return
    if not adapter.supports_zero_copy_clone():
        target_context: str = (
            f"target '{destination_target_name}' has reuse_from = '{reuse_from_target_name}', but "
            if destination_target_name is not None and reuse_from_target_name is not None
            else ""
        )
        raise ExecutorInputError(
            f"{target_context}adapter '{adapter.adapter_name}' does not support cheap "
            "relation reuse with reuse_hard_copy = false. "
            "SQLBuild will not copy production relations automatically because copying large "
            "tables can be expensive. Set reuse_hard_copy = true for this target to force "
            "copy-based reuse, "
            "or remove reuse_from to build normally."
        )
    adapter.clone(
        connection,
        origin=origin_relation,
        destination=destination_relation,
        hard_copy=False,
        origin_is_transient=origin_is_transient,
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
) -> Fingerprint:
    """Validate and create a concrete destination relation from a reuse plan."""

    reuse_origin_fingerprint: Fingerprint = validate_reuse_origin_fingerprint(
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
        origin_is_transient=_origin_is_transient(
            adapter=adapter, connection=connection, location=relation_reuse.origin
        ),
        destination_target_name=relation_reuse.destination_target_name,
        reuse_from_target_name=relation_reuse.reuse_from_target_name,
    )
    return reuse_origin_fingerprint


def validate_reuse_origin_fingerprint(
    *,
    adapter: BaseAdapter,
    connection: Any,
    model_name: str,
    expected_version_hash: str | None,
    reuse_from_target_name: str | None,
    reuse_origin_fingerprint_database: str | None,
    reuse_origin_fingerprint_schema: str | None,
) -> Fingerprint:
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
        table_exists=adapter.relation_exists(
            connection,
            database=reuse_origin_fingerprint_database,
            schema=reuse_origin_fingerprint_schema,
            name=FINGERPRINT_TABLE_NAME,
        ),
        database=reuse_origin_fingerprint_database,
        schema=reuse_origin_fingerprint_schema,
        render_qualified_name=adapter.render_qualified_name,
        render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
        require_table=True,
    )
    reuse_origin_fingerprint: Fingerprint | None = fingerprint_set.fingerprints.get(model_name)
    if (
        reuse_origin_fingerprint is None
        or reuse_origin_fingerprint.version_hash != expected_version_hash
    ):
        raise ExecutorInputError(
            f"model '{model_name}' cannot reuse from target '{reuse_from_target_name}' because "
            "the reuse origin fingerprint changed after planning. Rerun the plan and try again."
        )
    return reuse_origin_fingerprint
