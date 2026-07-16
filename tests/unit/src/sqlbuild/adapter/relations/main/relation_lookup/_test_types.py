from dataclasses import dataclass


@dataclass(frozen=True)
class RelationLookupTestCase:
    description: str
    warehouse_relations: tuple[tuple[str | None, str, bool | None], ...]
    locations: tuple[tuple[str | None, str | None, str], ...]
    probe_schema: str | None
    probe_name: str
    expected_exists: bool
    expected_is_transient: bool
    expected_list_relations_calls: int
    expected_queried_relation_calls: tuple[tuple[str | None, tuple[str, ...]], ...]
    probe_database: str | None = None
