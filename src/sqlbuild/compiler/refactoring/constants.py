"""Constants for project refactorings."""

from __future__ import annotations

import re

from sqlbuild.compiler.refactoring.types import (
    RefactorOperation,
)

MODEL_KIND_PREFIX: str = "model:"
IDENTIFIER_CHARACTERS: str = r"A-Za-z0-9_$"
MIGRATE_FROM_KEY: str = "migrate_from"
SQL_LIKE_PATTERN: re.Pattern[str] = re.compile(r"\b(select|from|join|insert|update)\b", re.I)
OPERATION_TITLES: dict[RefactorOperation, str] = {
    RefactorOperation.RENAME_MODEL: "Rename model",
    RefactorOperation.MOVE_MODEL: "Move model",
    RefactorOperation.RENAME_COLUMN: "Rename column",
}
GENERIC_DIALECT: str = "generic"
