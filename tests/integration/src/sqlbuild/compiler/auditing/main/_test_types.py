from dataclasses import dataclass, field

from sqlbuild.spec.models.source import SourceEntry


@dataclass(frozen=True)
class ExecuteRenderedAuditTestCase:
    description: str
    setup_sql: tuple[str, ...]
    unresolved_sql: str
    model_targets: dict[str, str]
    source_map: dict[str, SourceEntry]
    expected_row_count: int
    relation_overrides: dict[str, str] = field(default_factory=dict)
