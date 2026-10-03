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
    detects_duplicates: bool = False
    cache_enabled: bool = True


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


@dataclass(frozen=True)
class HostCancellationTestCase:
    """A fast failure on one host while the other hosts are still busy."""

    description: str
    model_count: int
    hosts: int
    timeout_millis: int
    delay_seconds: float
    expected_error_fragment: str
    expected_max_seconds: float


@dataclass(frozen=True)
class HostCapacityTestCase:
    """Fake cgroup files and the CPU count they allow."""

    description: str
    proc_cgroup: str
    files: dict[str, str]
    expected_cores: int
