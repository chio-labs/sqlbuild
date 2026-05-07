from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class ContractValidationTestCase:
    description: str
    declared_columns: tuple[tuple[str, str | None], ...]
    inferred_columns: tuple[tuple[str, str | None], ...] | None
    type_enforcement: bool | None
    expected_codes: tuple[str, ...]
    expected_severities: tuple[str, ...]
    expected_messages: tuple[str, ...]
    declared_not_null_columns: tuple[str, ...] = ()
    declared_nullable_by_column: dict[str, bool | None] | None = None
    inferred_nullability_by_column: dict[str, InferredNullability] | None = None


@dataclass(frozen=True)
class ContractLocationTestCase:
    description: str
    column_name: str
    path: Path
    line: int
    column: int
    expected_path: Path
    expected_line: int
    expected_column: int
