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


@dataclass(frozen=True)
class StaleRootCausesTestCase:
    description: str
    stale_model_names: tuple[str, ...]
    stale_root_reasons: dict[str, PlanReason]
    expected_stale_root_causes: dict[str, str]
