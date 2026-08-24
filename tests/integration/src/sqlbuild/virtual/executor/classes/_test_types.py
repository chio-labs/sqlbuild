"""Test types for virtual executor class integration tests."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualMicrobatchLeaseManagerTestCase:
    """Expected renewable lease behavior for one manager lifecycle."""

    description: str
    renew_interval_seconds: float
    expected_loss_fragment: str
