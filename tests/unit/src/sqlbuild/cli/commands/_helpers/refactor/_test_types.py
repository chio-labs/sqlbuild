"""Test case types for refactor output tests."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.refactoring.types import RefactorOperation, RefactorStatus


@dataclass(frozen=True)
class RefactorStatusLineTestCase:
    description: str
    status: RefactorStatus
    changed_files: int
    expected_line: str


@dataclass(frozen=True)
class RefactorTargetTestCase:
    description: str
    command: str
    target: str
    cascade: bool
    expected_operation: RefactorOperation
    expected_model_name: str
    expected_column_name: str | None


@dataclass(frozen=True)
class RefactorTargetErrorTestCase:
    description: str
    command: str
    target: str
    cascade: bool
    expected_message: str
    expected_help: str | None


@dataclass(frozen=True)
class LayerMoveSuggestionTestCase:
    description: str
    old_path: str
    new_name: str
    codes: tuple[str, ...]
    expected_command: str | None
    expected_folder: str | None
