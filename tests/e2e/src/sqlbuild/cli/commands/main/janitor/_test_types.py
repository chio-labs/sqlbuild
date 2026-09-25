"""Test types for janitor e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JanitorDisabledE2ETestCase:
    """Test case for disabled janitor command behavior."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class JanitorCleanupE2ETestCase:
    """Test case for tracked-only janitor cleanup behavior."""

    description: str
    build_command: tuple[str, ...]
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_existing_tables: tuple[str, ...]
    expected_missing_tables: tuple[str, ...]
    expected_archived_original_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class JanitorSourceOverlapE2ETestCase:
    """Test case for fail-closed source and managed schema overlap."""

    description: str
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_existing_relations: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class JanitorInvalidConfigE2ETestCase:
    """Test case for invalid janitor config behavior."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stderr_fragments: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class JanitorDirectStatePruningE2ETestCase:
    description: str
    build_command: tuple[str, ...]
    janitor_command: tuple[str, ...]
    plan_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_fingerprint_count_before: int
    expected_fingerprint_count_after: int
    expected_source_freshness_count_before: int
    expected_source_freshness_count_after: int
    expected_fingerprint_run_ids_after: tuple[str, ...]
    expected_source_freshness_run_ids_after: tuple[str, ...]


@dataclass(frozen=True)
class JanitorArchiveRetentionE2ETestCase:
    """Test case for direct-mode archival after the relation retention period."""

    description: str
    janitor_command: tuple[str, ...]
    retired_model_ages_days: dict[str, int]
    expected_archived_names: tuple[str, ...]
    expected_retained_names: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_second_run_fragments: tuple[str, ...]


@dataclass(frozen=True)
class JanitorArchiveExpiryE2ETestCase:
    """Test case for name-based deletion of expired archives."""

    description: str
    janitor_command: tuple[str, ...]
    expected_deleted_names: tuple[str, ...]
    expected_kept_names: tuple[str, ...]
    expected_kept_other_schema_names: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_delete_event_count: int
    expected_total_event_count: int


@dataclass(frozen=True)
class JanitorZeroRetentionE2ETestCase:
    """Test case for archive and delete in one run."""

    description: str
    janitor_command: tuple[str, ...]
    stale_tables: tuple[str, ...]
    stale_views: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_event_types: tuple[tuple[str, str], ...]
    expected_fingerprint_count_after: int
    expected_source_freshness_count_after: int


@dataclass(frozen=True)
class JanitorArchiveNameFittingE2ETestCase:
    """Test case for identifier-fitted archive names."""

    description: str
    janitor_command: tuple[str, ...]
    long_relation_name: str
    identifier_limit: int
    expected_archive_prefix_length: int


@dataclass(frozen=True)
class JanitorArchiveInterruptionE2ETestCase:
    """Test case for an audit write failure after a rename."""

    description: str
    janitor_command: tuple[str, ...]
    stale_table: str
    expected_first_exit_code: int
    expected_first_output_fragments: tuple[str, ...]
    expected_second_exit_code: int
    expected_second_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class JanitorUnaddressableRelationE2ETestCase:
    """Test case for relations the janitor cannot safely address unquoted."""

    description: str
    janitor_command: tuple[str, ...]
    plain_relation: str
    quoted_relation: str
    expected_stdout_fragments: tuple[str, ...]
