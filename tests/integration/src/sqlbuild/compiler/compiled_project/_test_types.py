"""Test case types for native compiled project integration tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetainedRulesRowsTestCase:
    """A real compile whose rules request reads model facts the compile-input stage retained."""

    description: str
    engine: str
    expected_codes: tuple[str, ...]


@dataclass(frozen=True)
class UnretainedRulesRowsTestCase:
    """A compile whose model facts were not retained, so rules cannot read them."""

    description: str
    expected_error: str
