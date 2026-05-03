from dataclasses import dataclass, field


@dataclass(frozen=True)
class RenderAuditSqlTestCase:
    description: str
    unresolved_sql: str
    model_targets: dict[str, str]
    source_map_entries: dict[str, tuple[str | None, str | None, str | None]]
    expected_sql_fragment: str
    relation_overrides: dict[str, str] = field(default_factory=dict)
    seed_targets: dict[str, str] = field(default_factory=dict)
