"""Test case types for the shared E2E command helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HangDumpTestCase:
    """A Python command that never finishes and what its hang report must show."""

    description: str
    script: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class FinishedCommandTestCase:
    """A Python command that finishes and the result the helper must return for it."""

    description: str
    script: str
    input_text: str | None
    expected_result: tuple[int, str, str]
