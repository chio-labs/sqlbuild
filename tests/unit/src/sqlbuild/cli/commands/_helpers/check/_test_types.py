"""Test case types for Python check CLI projection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckOutputProjectionCase:
    description: str
    expected_first_duration: str
    expected_second_duration: str
    expected_generic_terminal_count: int
