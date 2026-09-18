"""Test types for query-diff artifact integration coverage."""

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryArtifactCleanupTestCase:
    """One query-artifact cleanup integration case."""

    description: str
    expected_fingerprint_count: int
