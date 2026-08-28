from dataclasses import dataclass
from pathlib import Path

from sqlbuild.cost.types import CostStatus


@dataclass(frozen=True)
class AllocationTestCase:
    description: str
    expected_status: CostStatus


@dataclass(frozen=True)
class RenderQueryHistorySqlTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    expected_excluded_fragment: str


@dataclass(frozen=True)
class ParseQueryTagTestCase:
    description: str
    query_tag: str | None
    expected_payload: dict[str, object] | None


@dataclass(frozen=True)
class CollectSnowflakeCostTestCase:
    description: str
    expected_status: CostStatus
    expected_query_count: int
    expected_resource_name: str
    expected_limitation_fragment: str = ""


@dataclass(frozen=True)
class SnowflakeObservationTestCase:
    description: str
    warehouse_name: str | None
    warehouse_size: str | None
    execution_ms: int
    execution_status: str
    expected_status: CostStatus
    expected_query_count: int
    expected_limitation_fragment: str = ""
    query_type: str = "SELECT"
    query_text: str = "SELECT * FROM orders"


@dataclass(frozen=True)
class SnowflakeStatementClassificationTestCase:
    description: str
    query_type: str
    query_text: str
    expected_metadata_only: bool


@dataclass(frozen=True)
class SnowflakeClockSkewTestCase:
    description: str
    snowflake_offset_seconds: int
    expected_status: CostStatus
    expected_query_count: int
    expected_attributed_seconds: str


@dataclass(frozen=True)
class SnowflakeSaturationTestCase:
    description: str
    expected_saturated: bool
    expected_observed_query_ids: frozenset[str]


@dataclass(frozen=True)
class CostStoreTestCase:
    description: str
    expected_run_ids: tuple[str, ...]
    expected_resolved: bool = True


@dataclass(frozen=True)
class InvalidCostArtifactTestCase:
    description: str
    old_fragment: str
    new_fragment: str
    expected_run_ids: tuple[str, ...]


@dataclass(frozen=True)
class InvalidCostRunIdTestCase:
    description: str
    run_id: str
    expected_error_fragment: str


@dataclass(frozen=True)
class CostResourceScopeTestCase:
    description: str
    ledger_path: Path
    expected_resource_type: str
    expected_resource_name: str
    expected_phase: str
    expected_attempt: int
