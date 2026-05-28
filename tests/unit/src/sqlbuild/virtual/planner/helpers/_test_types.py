from dataclasses import dataclass

from sqlbuild.compiler.planner.types import PlanReason


@dataclass(frozen=True)
class ExpectedVersionHashesTestCase:
    description: str
    upstream_query_sql: str
    downstream_query_sql: str
    expected_hashes_differ: bool


@dataclass(frozen=True)
class DefaultVirtualSelectionTestCase:
    description: str
    stale_model_names: tuple[str, ...]
    expected_selection: tuple[str, ...]


@dataclass(frozen=True)
class VirtualModelSelectionTestCase:
    description: str
    select: tuple[str, ...]
    default_selection: tuple[str, ...]
    stale_model_names: tuple[str, ...]
    include_stale_upstreams: bool
    changes_only: bool
    expected_selection: tuple[str, ...]
    downstream_depends_on_dim_customers: bool = False


@dataclass(frozen=True)
class StaleRequiredUpstreamClosureTestCase:
    description: str
    selected_model_names: tuple[str, ...]
    stale_model_names: tuple[str, ...]
    expected_stale_upstream_names: tuple[str, ...]


@dataclass(frozen=True)
class StaleModelNamesTestCase:
    description: str
    expected_version_hashes: dict[str, str]
    bound_version_hashes: dict[str, str]
    expected_stale_model_names: tuple[str, ...]


@dataclass(frozen=True)
class StaleRootReasonsTestCase:
    description: str
    stale_model_names: tuple[str, ...]
    expected_local_hashes: dict[str, str]
    bound_version_hashes: dict[str, str]
    bound_local_hashes: dict[str, str]
    expected_stale_root_reasons: dict[str, PlanReason]
    current_query_sqls: dict[str, str] | None = None
    bound_previous_query_sqls: dict[str, str] | None = None
    expected_metadata_jsons: dict[str, str] | None = None
    bound_metadata_jsons: dict[str, str] | None = None


@dataclass(frozen=True)
class StaleRootCausesTestCase:
    description: str
    stale_model_names: tuple[str, ...]
    stale_root_reasons: dict[str, PlanReason]
    expected_stale_root_causes: dict[str, str]
    stale_root_source_causes: dict[str, str] | None = None


@dataclass(frozen=True)
class StaleRootCauseReasonsTestCase:
    description: str
    stale_root_reasons: dict[str, PlanReason]
    stale_root_source_causes: dict[str, str]
    expected_stale_root_cause_reasons: dict[str, PlanReason]


@dataclass(frozen=True)
class StaleRootSourceCausesTestCase:
    description: str
    stale_root_reasons: dict[str, PlanReason]
    expected_metadata_jsons: dict[str, str]
    bound_metadata_jsons: dict[str, str]
    expected_stale_root_source_causes: dict[str, str]
