from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.executor.janitor.models import (
    JanitorArchiveCandidate,
    JanitorArchivedRelation,
    JanitorBlockedSchema,
    JanitorDeleteCandidate,
    JanitorPlan,
    JanitorRelationKey,
    JanitorSkippedRelation,
    JanitorSkippedSchema,
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
        blocked_schemas=(
            JanitorBlockedSchema(
                database=None,
                schema="blocked",
                source_names=("raw.events",),
                suppressed_candidates=(
                    JanitorDeleteCandidate(
                        key=JanitorRelationKey(
                            database=None,
                            schema="blocked",
                            name="old_model",
                        ),
                        relation=RelationInfo(
                            database=None,
                            schema="blocked",
                            name="old_model",
                            relation_type="table",
                        ),
                        age_timestamp=None,
                    ),
                ),
            ),
        ),
        scanned_schema_count=2,
        age_metadata_supported=True,
    )


def build_direct_archive_plan() -> JanitorPlan:
    archived_at: datetime = datetime(2026, 9, 24, 10, 15, 0, tzinfo=UTC)
    relation: RelationInfo = RelationInfo(
        database=None,
        schema="dev",
        name="old_orders",
        relation_type="table",
    )
    original_key: JanitorRelationKey = JanitorRelationKey(
        database=None, schema="dev", name="old_orders"
    )
    return JanitorPlan(
        target_name="dev",
        retention_days=14,
        direct_mode=True,
        archive_retention_days=14,
        candidates=(
            JanitorDeleteCandidate(key=original_key, relation=relation, age_timestamp=None),
        ),
        archive_candidates=(
            JanitorArchiveCandidate(
                key=original_key,
                relation=relation,
                age_timestamp=archived_at - timedelta(days=20),
                archive_key=JanitorRelationKey(
                    database=None,
                    schema="dev",
                    name="_sqb_archive__20260924t101500z__old_orders",
                ),
                archived_at=archived_at,
                expires_at=archived_at + timedelta(days=14),
            ),
        ),
        archive_deletion_candidates=(
            JanitorArchivedRelation(
                key=JanitorRelationKey(
                    database=None,
                    schema="dev",
                    name="_sqb_archive__20260101t000000z__old_products",
                ),
                relation_type="table",
                archived_at=datetime(2026, 1, 1, tzinfo=UTC),
                expires_at=datetime(2026, 1, 15, tzinfo=UTC),
            ),
        ),
        age_metadata_supported=True,
        planned_at=archived_at,
    )
