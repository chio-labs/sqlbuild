"""Test case types for executor column rename helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverlappingColumnRenameTestCase:
    description: str
    transactional: bool
    expected_columns: tuple[str, ...]
    expected_decisions: tuple[str, ...]
