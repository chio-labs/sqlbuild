"""Test case types for worker completion helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerCompletionTestCase:
    description: str
    key: str
    connection: str
    execute: Callable[[object], str]
    expected_completion: tuple[str, str]
    expected_connection: str
