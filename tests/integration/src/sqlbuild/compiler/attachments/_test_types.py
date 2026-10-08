from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthoredSqlParityTestCase:
    """Seeded authored SQL expanded by the Python engine and by the preview engine."""

    description: str
    seed: int
    count: int
    expected_minimum_expanded: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class AttachedAuditParityTestCase:
    """Seeded attached audits rendered natively and by Python's attachment helpers."""

    description: str
    seed: int
    count: int
    expected_minimum_native: int
    expected_minimum_deferred: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class AttachmentProjectTestCase:
    """One project variant compiled to compile inputs by each engine."""

    description: str
    expected_preview_entries: frozenset[str]


@dataclass(frozen=True)
class CursorIntrinsicParityTestCase:
    """Seeded SQL checked for cursor intrinsics natively and by Python."""

    description: str
    seed: int
    count: int
    expected_minimum_free: int
    expected_minimum_python_errors: int
