"""Staging relation creation for staged table promotion."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import RelationReuseKind
from sqlbuild.executor.run._helpers.reuse.core import create_relation_from_reuse_plan
from sqlbuild.executor.run.models import ModelMaterializationContext


def create_staging_relation(
    *,
    context: ModelMaterializationContext,
    staging_qualified: str,
    resolved_sql: str,
    statement_recorder: StatementRecorder,
) -> Fingerprint | None:
    """Create the staging relation via reuse plan or CTAS; return the reuse fingerprint."""

    entry: ModelPlanEntry = context.entry
    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    adapter.drop(
        connection=connection,
        destination=staging_qualified,
        if_exists=True,
        statement_recorder=statement_recorder,
    )
    if (
        entry.relation_reuse is not None
        and entry.relation_reuse.kind == RelationReuseKind.COMPLETE_RELATION_REUSE
    ):
        return create_relation_from_reuse_plan(
            adapter=adapter,
            connection=connection,
            model_name=entry.name,
            expected_version_hash=entry.fingerprint_version_hash,
            relation_reuse=entry.relation_reuse,
            destination_relation=staging_qualified,
            statement_recorder=statement_recorder,
        )
    adapter.create_table_as(
        connection=connection,
        destination=staging_qualified,
        sql=resolved_sql,
        statement_recorder=statement_recorder,
    )
    return None
