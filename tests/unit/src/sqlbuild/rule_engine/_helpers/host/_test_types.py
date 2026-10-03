"""Test case declarations for custom-rule host partitioning."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HostPartitionTestCase:
    """One partitioned custom-rule evaluation compared with a single host."""

    description: str
    model_count: int
    hosts: int
    expected_host_runs: int
    records_module_state: bool = False


@dataclass(frozen=True)
class HostFailureTestCase:
    """Failing subjects whose first single-host failure must be reported."""

    description: str
    model_count: int
    failing_models: tuple[str, ...]
    expected_failing_model: str


@dataclass(frozen=True)
class HostPlanTestCase:
    """One deterministic split of planned invocations."""

    description: str
    plan: dict[str, list[str] | None]
    invocations: tuple[tuple[str, str], ...]
    hosts: int
    expected_plans: tuple[dict[str, list[str] | None], ...]
