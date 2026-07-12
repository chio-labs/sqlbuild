"""Test case types for worker completion helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerCompletionTestCase:
    description: str
    key: str
    connection: str
    result: str | None
    expected_completion: tuple[str, str]
    expected_connection: str
    expected_error_fragment: str | None = None
