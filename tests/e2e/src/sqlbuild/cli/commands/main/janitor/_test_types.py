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


@dataclass(frozen=True)
class JanitorMicrobatchHistoryProtectionE2ETestCase:
    """Test case for immutable virtual microbatch history during janitor cleanup."""

    description: str
    janitor_command: tuple[str, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class JanitorCheckpointProtectionE2ETestCase:
    """Test case for virtual checkpoint-protected janitor cleanup behavior."""

    description: str
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class JanitorCheckpointRetentionE2ETestCase:
    """Test case for virtual checkpoint pruning behavior."""

    description: str
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_checkpoint_count_before: int
    expected_checkpoint_count_after: int
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class JanitorDetachedVirtualEnvironmentE2ETestCase:
    """Test case for detached VDE cleanup behavior."""

    description: str
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_virtual_environment_count_after: int
    expected_ref_count_after: int


@dataclass(frozen=True)
class JanitorDetachedVirtualEnvironmentRetentionE2ETestCase:
    """Test case for detached VDE retention age behavior."""

    description: str
    retention_days: int
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_virtual_environment_count_after: int


@dataclass(frozen=True)
class JanitorActiveVirtualEnvironmentProtectionE2ETestCase:
    """Test case for active VDE ref protection behavior."""

    description: str
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class JanitorExpiredVirtualEnvironmentE2ETestCase:
    """Test case for expired non-active VDE cleanup behavior."""

    description: str
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_virtual_environment_names_after: tuple[str, ...]


@dataclass(frozen=True)
class JanitorStateCleanupE2ETestCase:
    """Test case for state-only janitor cleanup behavior."""

    description: str
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_backup_schema_count_after: int
    expected_lock_count_after: int


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
