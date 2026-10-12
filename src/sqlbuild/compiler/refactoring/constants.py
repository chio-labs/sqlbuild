"""Constants for project refactorings."""

from __future__ import annotations

from sqlbuild.compiler.refactoring.types import (
    RefactorOperation,
)

MODEL_KIND_PREFIX: str = "model:"
MIGRATE_FROM_KEY: str = "migrate_from"
OPERATION_TITLES: dict[RefactorOperation, str] = {
    RefactorOperation.RENAME_MODEL: "Rename model",
    RefactorOperation.MOVE_MODEL: "Move model",
    RefactorOperation.RENAME_COLUMN: "Rename column",
}
GENERIC_DIALECT: str = "generic"
