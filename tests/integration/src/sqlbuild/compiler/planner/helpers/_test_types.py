from dataclasses import dataclass, field

from sqlbuild.compiler.fingerprints.models import Fingerprint


@dataclass(frozen=True)
class GatherWarehouseSnapshotTestCase:
    description: str
    setup_sql: tuple[str, ...]
    model_targets: dict[str, str | None]
    seed_targets: dict[str, str | None]
    fingerprints_to_write: tuple[tuple[str, Fingerprint], ...] = field(default_factory=tuple)
    expected_relation_names: frozenset[str] = field(default_factory=frozenset)
    expected_column_table_names: frozenset[str] = field(default_factory=frozenset)
    expected_fingerprint_names: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class GatherEmptySnapshotTestCase:
    description: str
    expected_relation_count: int
    expected_column_count: int
    expected_fingerprint_count: int
