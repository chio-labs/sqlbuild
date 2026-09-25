from dataclasses import dataclass


@dataclass(frozen=True)
class HydrationLifecycleTestCase:
    description: str
    resource_kind: str
    resource_name: str
    expected_action: str | None
    expected_event_types: tuple[str, ...]


@dataclass(frozen=True)
class PhysicalTargetTestCase:
    description: str
    model_name: str
    version_hash: str
    expected_schema: str
    expected_name: str


@dataclass(frozen=True)
class RelationTypeTestCase:
    description: str
    materialized: str | None
    expected_relation_type: str


@dataclass(frozen=True)
class RewrittenTargetsTestCase:
    description: str
    selected_model_version_hashes: dict[str, str]
    bound_relations: dict[str, str]
    expected_selected_name: str
    expected_bound_name: str


@dataclass(frozen=True)
class RewriteProjectTargetsTestCase:
    description: str
    selected_model_version_hashes: dict[str, str]
    expected_rewritten_name: str


@dataclass(frozen=True)
class SeedingStrategyTestCase:
    description: str
    incremental_strategy: str
    supports_durable_clone: bool
    expected_strategy: str
    expected_sql_fragment: str


@dataclass(frozen=True)
class SeedingIdempotencyTestCase:
    description: str
    target_exists: bool
    expected_drop_count: int
    expected_ancestry_count: int
    expected_sql_count: int


@dataclass(frozen=True)
class SeedPhysicalRelationLookupTestCase:
    description: str
    seed_version_hashes: dict[str, str]
    available_seed_names: tuple[str, ...]
    expected_seed_names: tuple[str, ...]


@dataclass(frozen=True)
class MissingRollbackSeedRelationTestCase:
    description: str
    final_seed_hashes: dict[str, str]
    expected_error_fragment: str


@dataclass(frozen=True)
class VirtualPhaseTimingTestCase:
    description: str
    clock_values: tuple[float, ...]
    expected_compile_seconds: float
    expected_planning_seconds: float
    expected_total_seconds: float


@dataclass(frozen=True)
class VirtualStatementScopeTestCase:
    description: str
    expected_phases: tuple[str, ...]
    expected_callback_count: int
