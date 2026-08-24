from dataclasses import dataclass


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
