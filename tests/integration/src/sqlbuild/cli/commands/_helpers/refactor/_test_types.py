"""Test case types for refactor command integration tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RefactorStatusMessagesTestCase:
    description: str
    command: str
    target: str
    new_name: str | None
    destination: str | None
    expected_lines: tuple[str, ...]


@dataclass(frozen=True)
class BareTargetRefactorTestCase:
    description: str
    command: str
    target: str
    new_name: str | None
    destination: str | None
    expected_path: str
    expected_fragment: str
    expected_missing_paths: tuple[str, ...]
