"""Test case types for shared type helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlbuild.shared.types import SqlReferenceKind


@dataclass(frozen=True)
class SqlReferenceKindExampleCallTestCase:
    description: str
    reference_kind: SqlReferenceKind
    args: tuple[str, ...]
    quote: Literal["'", '"']
    expected_call: str
