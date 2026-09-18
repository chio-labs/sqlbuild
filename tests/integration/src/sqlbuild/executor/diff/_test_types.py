"""Test types for query-diff artifact integration coverage."""

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryArtifactCleanupTestCase:
    """One query-artifact cleanup integration case."""

    description: str
    expected_fingerprint_count: int


@dataclass(frozen=True)
class QueryArtifactCleanupFailureTestCase:
    """One mandatory current-run cleanup failure case."""

    description: str
    run_id: str
    expected_error: str
    expected_artifact_count: int
