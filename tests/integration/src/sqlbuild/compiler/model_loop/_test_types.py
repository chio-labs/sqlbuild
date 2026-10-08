from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeclarationReferenceParityTestCase:
    """Seeded SQL with `@enum`/`@const` references expanded natively and in Python."""

    description: str
    seed: int
    count: int
    expected_minimum_native_references: int
    expected_maximum_deferred: int
    expected_minimum_native_errors: int
