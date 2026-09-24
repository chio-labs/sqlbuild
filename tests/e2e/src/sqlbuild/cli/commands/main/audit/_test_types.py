"""Test types for audit command e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


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
