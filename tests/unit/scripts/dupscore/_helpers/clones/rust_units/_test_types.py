from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RustUnitsTestCase:
    description: str
    source: str
    include_tests: bool
    expected_units: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class RustTestModuleTestCase:
    description: str
    relative_path: str
    source: str
    expected_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class RustKeyTestCase:
    description: str
    left_source: str
    right_source: str
    expected_same_concrete: bool
    expected_same_normalized: bool
