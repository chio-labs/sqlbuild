"""Test case models for execution output helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MicrobatchExecutionProtocolTestCase:
    """Expected identifying fields in serialized microbatch execution output."""

    description: str
    expected_run_type: str
    expected_replay_state: str


@dataclass(frozen=True)
class FutureCursorExecutionProtocolTestCase:
    description: str
    expected_action: str


@dataclass(frozen=True)
class SqlTestCaseExecutionProtocolTestCase:
    """Expected identity and typed parameter fields for one SQL test case."""

    description: str
    expected_check_id: str
    expected_decimal_value: str
    expected_fingerprint: str
    expected_text_label: str


@dataclass(frozen=True)
class SqlTestDifferenceOutputTestCase:
    """Expected structured fields for SQL test difference output."""

    description: str
    expected_unexpected_count: int
    expected_missing_count: int


@dataclass(frozen=True)
class AuditExecutionProtocolTestCase:
    description: str
    expected_check_id: str
    expected_attachment_kind: str
    expected_target_kind: str
    expected_configured_concurrency: int = 1
    expected_worker_count: int = 1
