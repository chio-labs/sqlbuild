from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import CursorSnapshotScope, ModelCursorSnapshot
from sqlbuild.spec.contracts.models import SourceEntry


@dataclass(frozen=True)
class GatherWarehouseSnapshotTestCase:
    description: str
    setup_sql: tuple[str, ...]
    model_locations: dict[str, str | None]
    seed_locations: dict[str, str | None]
    selected_keys: frozenset[CompiledObjectKey] | None = None
    model_deps: dict[str, tuple[str, ...]] = field(default_factory=dict)
    fingerprints_to_write: tuple[tuple[str, Fingerprint], ...] = field(default_factory=tuple)
    expected_relation_names: frozenset[str] = field(default_factory=frozenset)
    expected_column_table_names: frozenset[str] = field(default_factory=frozenset)
    expected_fingerprint_names: frozenset[str] = field(default_factory=frozenset)
    expected_function_fingerprint_names: frozenset[str] = field(default_factory=frozenset)
    expected_seed_fingerprint_names: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class GatherEmptySnapshotTestCase:
    description: str
    expected_relation_count: int
    expected_column_count: int
    expected_fingerprint_count: int


@dataclass(frozen=True)
class GatherCursorSnapshotTestCase:
    description: str
    setup_sql: tuple[str, ...]
    selected_keys: frozenset[CompiledObjectKey] | None
    full_refresh: bool
    expected_cursor_model_names: frozenset[str]
    model_extra_config: dict[str, object] = field(default_factory=dict)
    expected_cursor_snapshots: dict[str, ModelCursorSnapshot] = field(default_factory=dict)
    expected_progress_calls: int = 0
    deferred_locations: dict[str, CompiledRelationLocation] | None = None
    extra_model_locations: dict[str, str | None] = field(default_factory=dict)
    cursor_scope: CursorSnapshotScope | None = None


@dataclass(frozen=True)
class GatherSharedCursorSnapshotTestCase:
    description: str
    expected_cursor_snapshot: ModelCursorSnapshot
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class GatherSelectedCursorScopeTestCase:
    description: str
    expected_cursor_snapshot: ModelCursorSnapshot
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class GatherOverrideCursorSnapshotTestCase:
    description: str
    expected_target_max: str
    expected_eligible_max: str | None
    expected_statement_count: int


@dataclass(frozen=True)
class GatherMixedGrainEligibilityTestCase:
    description: str
    expected_eligible_max: str
    expected_eligible_sql: str


@dataclass(frozen=True)
class GatherInvalidCursorScopeTestCase:
    description: str
    expected_error_code: str
    expected_error_fragment: str


@dataclass(frozen=True)
class GatherSourceColumnsTestCase:
    description: str
    setup_sql: tuple[str, ...]
    source_names: tuple[tuple[str, str, str], ...]
    expected_source_names: frozenset[str]
    expected_get_all_columns_names: tuple[tuple[str, ...] | None, ...]


@dataclass(frozen=True)
class ExecuteAuditTestCase:
    description: str
    setup_sql: tuple[str, ...]
    audit_sql: str
    model_locations: dict[str, str]
    source_map: dict[str, SourceEntry]
    expected_row_count: int
