"""Test case types for SQL reference declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlbuild.compiler.references.types import SqlReferenceKind


@dataclass(frozen=True)
class SqlReferenceKindExampleCallTestCase:
    description: str
    reference_kind: SqlReferenceKind
    args: tuple[str, ...]
    quote: Literal["'", '"']
    expected_call: str
