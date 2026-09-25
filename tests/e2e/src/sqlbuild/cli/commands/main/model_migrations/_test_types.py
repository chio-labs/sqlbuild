"""Test case types for model migration CLI e2e tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationLifecycleE2ETestCase:
    description: str
    expected_step_decisions: tuple[str, ...]
    expected_final_ids: tuple[int, ...]
    expected_previous_archive_ids: tuple[tuple[int, ...], ...]
    expected_events: tuple[tuple[str, str, str], ...]
