from dataclasses import dataclass

from sqlbuild.cost.types import CostStatus


@dataclass(frozen=True)
class CostCollectionTestCase:
    description: str
    expected_record_present: bool


@dataclass(frozen=True)
class CostOutputTestCase:
    description: str
    terminal_width: int
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CostRefreshTestCase:
    description: str
    selector: str
    expected_status: str
    initial_status: CostStatus = CostStatus.PENDING


@dataclass(frozen=True)
class CostRefreshDegradationTestCase:
    description: str
    candidate_status: CostStatus
    candidate_expected_statement_count: int
    candidate_observed_statement_count: int
    candidate_query_count: int
    expected_status: CostStatus
    expected_observed_statement_count: int
    expected_query_count: int
