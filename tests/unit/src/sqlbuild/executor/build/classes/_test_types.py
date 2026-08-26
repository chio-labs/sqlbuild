"""Test types for build scheduler class tests."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MicrobatchBoundedFutureTestCase:
    """Expected future bounds for one large microbatch phase."""

    description: str
    batch_count: int
    global_concurrency: int
    model_concurrency: int
    expected_max_subworker_futures: int


@dataclass(frozen=True)
class SqlTestAuthoredOrderTestCase:
    description: str
    case_names: tuple[str, ...]
    expected_order: tuple[str, ...]
