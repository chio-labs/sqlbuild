"""Test cases for typed SQL document facts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SqlDocumentTestCase:
    """One lazy SQL document projection expectation."""

    description: str
    source: str
    expected_cte_count: int
    expected_star_count: int
