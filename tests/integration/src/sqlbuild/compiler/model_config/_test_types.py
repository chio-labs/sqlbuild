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


@dataclass(frozen=True)
class ModelConfigTierTestCase:
    """One compiler engine and how often its model loop calls each native model config entry."""

    description: str
    engine: str
    expected_native_calls: dict[str, int]
