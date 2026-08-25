"""Test case models for microbatch projection and SQL behavior."""

from dataclasses import dataclass

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchInterval
from sqlbuild.microbatches.types import ReplayRequirementState


@dataclass(frozen=True)
class MicrobatchCoverageProjectionTestCase:
    """Expected physical and fingerprint coverage for one event history."""

    description: str
    events: tuple[MicrobatchEvent, ...]
    expected_intervals: tuple[MicrobatchInterval, ...]
    cursor_type: str
    expected_projected_intervals: tuple[tuple[str, str, str | None, str], ...]
    expected_known_missing: tuple[MicrobatchInterval, ...]
    expected_unaccounted: tuple[MicrobatchInterval, ...]
    expected_contiguous_frontier: str | None


@dataclass(frozen=True)
class MicrobatchReplayProjectionTestCase:
    """Expected state for one durable replay requirement projection."""

    description: str
    requirement: MicrobatchEvent
    current_model_version_hash: str
    events: tuple[MicrobatchEvent, ...]
    expected_intervals: tuple[MicrobatchInterval, ...]
    expected_state: ReplayRequirementState
    expected_missing: tuple[MicrobatchInterval, ...]
    expected_unknown_fingerprints: tuple[MicrobatchInterval, ...]


@dataclass(frozen=True)
class MicrobatchDdlAdapterTestCase:
    """One adapter expected to render the complete direct state table."""

    description: str
    adapter: BaseAdapter
    expected_table_name: str


@dataclass(frozen=True)
class MicrobatchSqlBehaviorTestCase:
    """Expected SQL shape for one direct-state behavior test."""

    description: str
    expected_statement_count: int
