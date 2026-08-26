"""Test case models for execution output helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MicrobatchExecutionProtocolTestCase:
    """Expected identifying fields in serialized microbatch execution output."""

    description: str
    expected_run_type: str
    expected_replay_state: str


@dataclass(frozen=True)
class SqlTestCaseExecutionProtocolTestCase:
    """Expected identity and typed parameter fields for one SQL test case."""

    description: str
    expected_check_id: str
    expected_decimal_value: str
    expected_fingerprint: str
    expected_text_label: str
