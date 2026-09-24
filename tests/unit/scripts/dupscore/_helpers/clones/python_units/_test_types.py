from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PythonUnitsTestCase:
    description: str
    source: str
    expected_units: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class PythonKeyTestCase:
    description: str
    left_source: str
    right_source: str
    expected_same_concrete: bool
    expected_same_normalized: bool
