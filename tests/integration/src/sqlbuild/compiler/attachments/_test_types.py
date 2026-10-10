from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttachedAuditParityTestCase:
    """Seeded attached audits rendered natively and by Python's attachment helpers."""

    description: str
    seed: int
    count: int
    expected_minimum_native: int
    expected_minimum_native_errors: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class BodyCallParityTestCase:
    """Seeded helper bodies whose call reading the native extractor shares with a Python scanner."""

    description: str
    seed: int
    count: int
    expected_minimum_calls: int
