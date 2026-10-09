"""Test case types for native type normalization parity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedTypeParityTestCase:
    """Seeded generated type strings normalized under every dialect."""

    description: str
    seed: int
    count: int
    expected_minimum_native: int
    expected_minimum_parse_errors: int
    expected_minimum_deferred: int


@dataclass(frozen=True)
class TypeParityTestCase:
    """One type string normalized natively and by Python under every dialect."""

    description: str
    type_sql: str
    expected_native_dialects: frozenset[str | None]


@dataclass(frozen=True)
class DeepTypeTestCase:
    """A type deeper than the wheel can parse, which only native sees."""

    description: str
    type_sql: str
    expected_native: None


@dataclass(frozen=True)
class PublicNativeTypeTestCase:
    """Types normalized through the public entry point under the preview engine."""

    description: str
    engine: str
    dialect: str
    type_strings: tuple[str, ...]
    expected_native_calls: tuple[tuple[str, str], ...]
    expected_answered: int
