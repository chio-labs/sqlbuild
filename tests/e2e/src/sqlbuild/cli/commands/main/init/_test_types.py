"""Test types for init e2e tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InitE2ETestCase:
    """Test case for sqb init e2e verification."""

    description: str
    expected_exit_code: int
    expected_paths: tuple[str, ...]
    expected_output_fragments: tuple[str, ...]
