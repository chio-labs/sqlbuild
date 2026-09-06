"""Dataclass-backed native audit result integration cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditResultWriteTestCase:
    """One append-only audit result write scenario."""

    description: str
    expected_row_count: int
