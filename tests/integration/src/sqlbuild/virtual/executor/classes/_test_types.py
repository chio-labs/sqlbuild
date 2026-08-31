"""Test types for virtual executor class integration tests."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualMicrobatchLeaseManagerTestCase:
    """Expected renewable lease behavior for one manager lifecycle."""

    description: str
    renew_interval_seconds: float
    expected_loss_fragment: str


@dataclass(frozen=True)
class VirtualSharedFullRefreshTestCase:
    """Incremental mode that must preserve a referenced physical version."""

    description: str
    incremental_strategy: str
    incremental_mode: str | None = None
    expected_error_fragment: str = "cannot replace a shared physical version"


@dataclass(frozen=True)
class VirtualConcurrentLeaseTestCase:
    """Incremental mode whose full refresh must serialize by physical version."""

    description: str
    incremental_strategy: str
    incremental_mode: str | None
    expected_conflict_fragment: str = "physical version is already being mutated"
    expected_shared_fragment: str = "cannot replace a shared physical version"


@dataclass(frozen=True)
class VirtualLeaseCancellationTestCase:
    """Expected lock cleanup when acquisition is cancelled after fencing."""

    description: str
    expected_error_type: type[BaseException]
    expected_remaining_lock_count: int
