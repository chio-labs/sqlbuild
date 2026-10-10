"""Enums and type aliases for project refactorings."""

from __future__ import annotations

from enum import StrEnum


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


class NativeRefactorErrorKind(StrEnum):
    """Which exception a native refactoring failure becomes."""

    INPUT = "input"
    EDIT = "edit"
    WRITE = "write"
    VALUE = "value"
    IO = "io"


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
