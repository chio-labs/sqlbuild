"""Test case models for execution output helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MicrobatchExecutionProtocolTestCase:
    """Expected identifying fields in serialized microbatch execution output."""

    description: str
    expected_run_type: str
    expected_replay_state: str
