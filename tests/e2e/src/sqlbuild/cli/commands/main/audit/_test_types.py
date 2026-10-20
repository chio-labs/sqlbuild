"""Test types for audit command e2e tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AuditE2ETestCase:
    """Test case for sqb audit e2e verification."""

    description: str
    expected_exit_code: int
    expected_stdout_fragment: str
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_ordered_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IncrementalAuditEventE2ETestCase:
    """One command whose audit_completed events must arrive during execution."""

    description: str
    setup_command: tuple[str, ...]
    command: tuple[str, ...]
    expected_audit_count: int


@dataclass(frozen=True)
class SlowSinkDropE2ETestCase:
    """A short lifecycle drain against a deliberately slow sink."""

    description: str
    shutdown_timeout: str
    expected_accepted: int
    expected_last_line: str


@dataclass(frozen=True)
class SlowSinkFullDeliveryE2ETestCase:
    """A generous lifecycle drain against a deliberately slow sink."""

    description: str
    shutdown_timeout: str
    expected_delivered: int


@dataclass(frozen=True)
class InvalidDrainTimeoutE2ETestCase:
    """One invalid lifecycle drain timeout value."""

    description: str
    shutdown_timeout_toml: str
    expected_error: str


@dataclass(frozen=True)
class AuditMetaRoundTripE2ETestCase:
    """Declared audit meta and where each audit's meta must reappear unchanged."""

    description: str
    prepare_results_table: Callable[[Path], None]
    expected_meta: dict[str, object]


@dataclass(frozen=True)
class AuditMetaChangeE2ETestCase:
    """One header edit whose rebuild is compared with an equivalent description-only edit."""

    description: str
    original_header_fragment: str
    meta_only_fragment: str
    description_only_fragment: str
    expected_meta_after_change: dict[str, object]
    expected_plan_reasons: dict[str, str]


@dataclass(frozen=True)
class InvalidAuditMetaE2ETestCase:
    """One project file whose audit meta must fail compilation with a clear message."""

    description: str
    relative_path: str
    contents: str
    expected_fragments: tuple[str, ...]
