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


@dataclass(frozen=True)
class SeedJsonOutputTestCase:
    """Expected canonical standalone seed JSON output."""

    description: str
    expected_exit_code: int
    expected_status: str
    expected_summary: dict[str, int]
    expected_assets: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class VirtualSeedE2ETestCase:
    """Test case for virtual sqb seed e2e verification."""

    description: str
    expected_seed_rows: tuple[tuple[object, ...], ...]
    expected_seed_fragments: tuple[str, ...]
    expected_current_seed_fragments: tuple[str, ...]
    expected_build_fragments: tuple[str, ...]
    unexpected_build_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_json_command: str = "seed"
    expected_json_reason: str = "no_change"
