"""Dataclass-backed audit result SQL test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditResultSqlTestCase:
    """One audit result SQL golden."""

    description: str
    expected_sql: str
