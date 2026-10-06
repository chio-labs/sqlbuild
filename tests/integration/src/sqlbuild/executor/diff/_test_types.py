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


@dataclass(frozen=True)
class FullDiffSizeGuardPassTestCase:
    """One guarded full diff that is allowed to read data."""

    description: str
    left_max_rows: int | None
    right_max_rows: int | None
    expected_metadata_lookups: int


@dataclass(frozen=True)
class FullDiffSizeGuardBlockTestCase:
    """One guarded full diff that must stop before reading data."""

    description: str
    left_max_rows: int | None
    right_max_rows: int | None
    right_relation_kind: str
    expected_left_row_count: int | None
    expected_right_row_count: int | None
    expected_left_exceeds: bool
    expected_right_exceeds: bool
