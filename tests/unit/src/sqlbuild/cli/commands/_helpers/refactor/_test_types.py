"""Test case types for refactor output tests."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.refactoring.types import RefactorStatus


@dataclass(frozen=True)
class RefactorStatusLineTestCase:
    description: str
    status: RefactorStatus
    changed_files: int
    expected_line: str
