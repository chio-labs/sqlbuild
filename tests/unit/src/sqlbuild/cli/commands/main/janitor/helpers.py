from __future__ import annotations

from datetime import datetime

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.executor.janitor.models import (
    JanitorCheckpointCandidate,
    JanitorDeleteCandidate,
    JanitorDetachedVirtualEnvironmentCandidate,
    JanitorExpiredLockCandidate,
    JanitorExpiredVirtualEnvironmentCandidate,
    JanitorPlan,
    JanitorRelationKey,
    JanitorSkippedRelation,
    JanitorSkippedSchema,
    JanitorStateBackupCandidate,
)


def build_janitor_plan() -> JanitorPlan:
    relation: RelationInfo = RelationInfo(
        database=None,
        schema="dev",
        name="stale_model",
        relation_type="table",
    )
    source_relation: RelationInfo = RelationInfo(
        database=None,
        schema="dev",
        name="source_table",
        relation_type="table",
    )
    return JanitorPlan(
        target_name="dev",
        retention_days=30,
        candidates=(
            JanitorDeleteCandidate(
                key=JanitorRelationKey(database=None, schema="dev", name="stale_model"),
                relation=relation,
                age_timestamp=None,
            ),
        ),
        checkpoint_candidates=(
            JanitorCheckpointCandidate(
                checkpoint_id="cp_1", virtual_environment_name="dev", created_at=None
            ),
        ),
        detached_virtual_environment_candidates=(
            JanitorDetachedVirtualEnvironmentCandidate(
                virtual_environment_name="branch_old", updated_at=None
            ),
        ),
        expired_virtual_environment_candidates=(
            JanitorExpiredVirtualEnvironmentCandidate(
                virtual_environment_name="branch_expired", updated_at=None
            ),
        ),
        state_backup_candidates=(
            JanitorStateBackupCandidate(
                backup_id="backup_1", schema_name="sqlbuild_state", created_at=None
            ),
        ),
        expired_lock_candidates=(
            JanitorExpiredLockCandidate(
                lock_key="lock_1",
                owner_id="worker_1",
                expires_at=datetime(2026, 5, 29),
            ),
        ),
        skipped_relations=(
            JanitorSkippedRelation(
                key=JanitorRelationKey(database=None, schema="dev", name="source_table"),
                reason="source relation",
                relation=source_relation,
            ),
        ),
        skipped_schemas=(
            JanitorSkippedSchema(
                database=None,
                schema="dev",
                source_names=("raw.orders",),
                skipped_relations=(source_relation,),
            ),
        ),
        scanned_schema_count=2,
        age_metadata_supported=True,
    )
