from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.adapter.shared.models import RelationInfo


@dataclass(frozen=True)
class JanitorPlanTestCase:
    description: str
    relation_infos: tuple[RelationInfo, ...]
    source_schema: str | None = None
    retention_days: int = 7
    delete_tracked_only: bool = False
    supports_age_metadata: bool = True
    tracked_relations: tuple[tuple[str | None, str | None, str], ...] = field(default_factory=tuple)
    exclude_patterns: tuple[str, ...] = field(default_factory=tuple)
    expected_candidate_names: tuple[str, ...] = field(default_factory=tuple)
    expected_skipped_relation_reasons: tuple[str, ...] = field(default_factory=tuple)
    expected_skipped_schema_sources: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class JanitorExecuteTestCase:
    description: str
    relation_infos: tuple[RelationInfo, ...]
    expected_dropped_targets: tuple[str, ...]


def relation_info(
    name: str,
    *,
    schema: str = "analytics",
    database: str | None = None,
    relation_type: str = "BASE TABLE",
    created_at: datetime | None = None,
    last_altered_at: datetime | None = None,
) -> RelationInfo:
    return RelationInfo(
        database=database,
        schema=schema,
        name=name,
        relation_type=relation_type,
        created_at=created_at,
        last_altered_at=last_altered_at,
    )
