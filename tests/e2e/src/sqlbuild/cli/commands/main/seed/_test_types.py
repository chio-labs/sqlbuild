"""Test types for seed e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeedE2ETestCase:
    """Test case for sqb seed e2e verification."""

    description: str
    expected_exit_code: int
    expected_seed_name: str
    expected_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
