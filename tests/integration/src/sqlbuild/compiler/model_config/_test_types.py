"""Test case types for the native model configuration parity tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeaderMetadataParityTestCase:
    """Seeded MODEL header metadata parsed natively and in Python."""

    description: str
    seed: int
    count: int
    expected_minimum_parsed: int
    expected_minimum_rejected: int
    expected_maximum_later_validated: int


@dataclass(frozen=True)
class ModelConfigTierTestCase:
    """How often the model loop calls each native model config entry."""

    description: str
    expected_native_calls: dict[str, int]


@dataclass(frozen=True)
class ColumnMetadataExpansionTestCase:
    """A header column field holding a config template or macro, and the loop's outcome."""

    description: str
    header_column: str
    expected_type: str | None
    expected_error: str | None
