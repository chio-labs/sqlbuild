"""CLI entrypoint test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputCaptureWiringTestCase:
    """Named singleton case for branch-free command wiring tests."""

    description: str
    expected_success: bool
