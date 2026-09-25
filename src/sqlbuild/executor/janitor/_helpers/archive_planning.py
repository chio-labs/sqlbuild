"""Direct-mode janitor archive and archive-expiry planning."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.executor.janitor._helpers.archive_names import (
    archive_timestamp,
    build_archive_name,
    is_archive_lookalike_name,
    parse_archive_name,
)
from sqlbuild.executor.janitor._helpers.classification import matching_exclude_pattern
from sqlbuild.executor.janitor._helpers.plan import relation_key as build_relation_key
from sqlbuild.executor.janitor._helpers.relation_addressing import (
    case_colliding_names,
    unaddressable_relation_reason,
)
from sqlbuild.executor.janitor.constants import BUILT_IN_EXCLUDE_PATTERNS, MALFORMED_ARCHIVE_REASON
from sqlbuild.executor.janitor.models import (
    JanitorArchiveCandidate,
    JanitorArchivedRelation,
    JanitorArchivePlanning,
    JanitorBlockedSchema,
    JanitorDeleteCandidate,
    JanitorParsedArchiveName,
    JanitorRelationKey,
    JanitorSchemaClassification,
    JanitorSkippedRelation,
    JanitorWarehouseFacts,
)


def plan_janitor_archives(
    *,
    direct_mode: bool,
    adapter: BaseAdapter,
    schemas: JanitorSchemaClassification,
    facts: JanitorWarehouseFacts,
    managed_target_schemas: set[tuple[str | None, str | None]],
    exclude_patterns: tuple[str, ...],
    archive_retention_days: int,
    now: datetime,
) -> JanitorArchivePlanning:
    """Plan direct-mode archives; virtual mode never archives or expires archives."""

    if not direct_mode:
        return JanitorArchivePlanning(
            archive_candidates=(),
            archive_deletion_candidates=(),
            retained_archives=(),
            skipped_relations=(),
            blocked_schemas=schemas.blocked_schemas,
        )
    return _plan_direct_archives(
        candidates=schemas.candidates,
        facts=facts,
        managed_target_schemas=managed_target_schemas,
        blocked_schemas=schemas.blocked_schemas,
        exclude_patterns=exclude_patterns,
        archive_retention_days=archive_retention_days,
        identifier_limit=adapter.maximum_identifier_length(),
        now=now,
    )


def _plan_direct_archives(
    *,
    candidates: tuple[JanitorDeleteCandidate, ...],
    facts: JanitorWarehouseFacts,
    managed_target_schemas: set[tuple[str | None, str | None]],
    blocked_schemas: tuple[JanitorBlockedSchema, ...],
    exclude_patterns: tuple[str, ...],
    archive_retention_days: int,
    identifier_limit: int,
    now: datetime,
) -> JanitorArchivePlanning:
    """Plan archive renames and name-based expiry of existing archives."""

    archived_at: datetime = archive_timestamp(now)
    retention: timedelta = timedelta(days=archive_retention_days)
    archive_candidates: tuple[JanitorArchiveCandidate, ...] = tuple(
        _archive_candidate(
            candidate=candidate,
            archived_at=archived_at,
            retention=retention,
            identifier_limit=identifier_limit,
        )
        for candidate in candidates
    )
    blocked_schema_keys: frozenset[tuple[str | None, str | None]] = frozenset(
        (blocked.database, blocked.schema) for blocked in blocked_schemas
    )
    deletions: list[JanitorArchivedRelation] = []
    retained: list[JanitorArchivedRelation] = []
    skipped: list[JanitorSkippedRelation] = []
    suppressed_by_schema: dict[tuple[str | None, str | None], list[JanitorArchivedRelation]] = {}
    effective_patterns: tuple[str, ...] = BUILT_IN_EXCLUDE_PATTERNS + exclude_patterns
    schema_key: tuple[str | None, str | None]
    for schema_key in sorted(managed_target_schemas, key=lambda key: (key[0] or "", key[1] or "")):
        schema_relations: tuple[RelationInfo, ...] = facts.relations_by_schema.get(schema_key, ())
        colliding_names: frozenset[str] = case_colliding_names(
            relation.name for relation in schema_relations
        )
        relation: RelationInfo
        for relation in schema_relations:
            key: JanitorRelationKey = build_relation_key(relation)
            if key in facts.desired_keys or not is_archive_lookalike_name(key.name):
                continue
            parsed: JanitorParsedArchiveName | None = parse_archive_name(key.name)
            if parsed is None:
                skipped.append(
                    JanitorSkippedRelation(
                        key=key, relation=relation, reason=MALFORMED_ARCHIVE_REASON
                    )
                )
                continue
            skip_reason: str | None = _archive_skip_reason(
                key=key, colliding_names=colliding_names, effective_patterns=effective_patterns
            )
            if skip_reason is not None:
                skipped.append(
                    JanitorSkippedRelation(key=key, relation=relation, reason=skip_reason)
                )
                continue
            archived: JanitorArchivedRelation = JanitorArchivedRelation(
                key=key,
                relation_type=relation.relation_type,
                archived_at=parsed.archived_at,
                expires_at=parsed.archived_at + retention,
            )
            if archived.expires_at > now:
                retained.append(archived)
            elif schema_key in blocked_schema_keys:
                suppressed_by_schema.setdefault(schema_key, []).append(archived)
            else:
                deletions.append(archived)
    same_run_deletions: tuple[JanitorArchivedRelation, ...] = tuple(
        JanitorArchivedRelation(
            key=candidate.archive_key,
            relation_type=candidate.relation.relation_type,
            archived_at=candidate.archived_at,
            expires_at=candidate.expires_at,
            original_key=candidate.key,
        )
        for candidate in archive_candidates
        if candidate.expires_at <= archived_at
    )
    return JanitorArchivePlanning(
        archive_candidates=archive_candidates,
        archive_deletion_candidates=(*deletions, *same_run_deletions),
        retained_archives=tuple(retained),
        skipped_relations=tuple(skipped),
        blocked_schemas=tuple(
            replace(
                blocked,
                suppressed_archive_deletions=tuple(
                    suppressed_by_schema.get((blocked.database, blocked.schema), ())
                ),
            )
            for blocked in blocked_schemas
        ),
    )


def _archive_skip_reason(
    *,
    key: JanitorRelationKey,
    colliding_names: frozenset[str],
    effective_patterns: tuple[str, ...],
) -> str | None:
    addressing_reason: str | None = unaddressable_relation_reason(
        name=key.name, colliding_names=colliding_names
    )
    if addressing_reason is not None:
        return addressing_reason
    exclude_pattern: str | None = matching_exclude_pattern(key=key, patterns=effective_patterns)
    if exclude_pattern is not None:
        return f"relation matches exclude pattern {exclude_pattern!r}"
    return None


def _archive_candidate(
    *,
    candidate: JanitorDeleteCandidate,
    archived_at: datetime,
    retention: timedelta,
    identifier_limit: int,
) -> JanitorArchiveCandidate:
    return JanitorArchiveCandidate(
        key=candidate.key,
        relation=candidate.relation,
        age_timestamp=candidate.age_timestamp,
        archive_key=JanitorRelationKey(
            database=candidate.key.database,
            schema=candidate.key.schema,
            name=build_archive_name(
                original_name=candidate.key.name,
                archived_at=archived_at,
                identifier_limit=identifier_limit,
            ),
        ),
        archived_at=archived_at,
        expires_at=archived_at + retention,
    )
