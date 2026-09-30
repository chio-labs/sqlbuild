"""Enums and type aliases for project refactorings."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol


class RefactorOperation(StrEnum):
    """One supported refactoring."""

    RENAME_MODEL = "rename_model"
    MOVE_MODEL = "move_model"
    RENAME_COLUMN = "rename_column"


class RefactorStatus(StrEnum):
    """Terminal state of one refactoring command."""

    APPLIED = "applied"
    DRY_RUN = "dry_run"
    REFUSED = "refused"
    COMPILE_FAILED = "compile_failed"


class EditKind(StrEnum):
    """What one text edit changes, for output grouping."""

    REFERENCE = "reference"
    FIXTURE = "fixture"
    HEADER = "header"
    COLUMN = "column"
    MIGRATION = "migration"


class SqlFileRole(StrEnum):
    """What an authored SQL file declares."""

    MODEL = "model"
    TEST = "test"
    SCENARIO = "scenario"
    AUDIT = "audit"
    HOOK = "hook"
    FUNCTION = "function"
    SCHEMA = "schema"
    YAML = "yaml"


class HeaderTokenKind(StrEnum):
    """MODEL header token kinds."""

    END = "end"
    WORD = "word"
    STRING = "string"
    SYMBOL = "symbol"


type ResourceColumns = dict[tuple[str, str], tuple[str, ...]]
type SpanMapper = Callable[[int, int], tuple[int, int] | None]
type OffsetLocator = Callable[[int], int]


class NativeColumnReferences(Protocol):
    """Native column-reference analysis boundary."""

    def analyze_column_references_json(self, request_json: str) -> str: ...
