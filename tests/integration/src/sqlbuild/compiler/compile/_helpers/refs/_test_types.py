from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import SqlReferenceSourceMap
from sqlbuild.compiler.frontier.types import CompilerEngine


@dataclass(frozen=True)
class CraftedReferenceTestCase:
    """One SQL text and how many calls the native scan rejects or fails on."""

    description: str
    sql: str
    expected_rejected: int = 0
    expected_failed: int = 0


@dataclass(frozen=True)
class ReferenceEngineTestCase:
    """Reference extraction through the compiler entry point under one engine."""

    description: str
    engine: CompilerEngine
    sql: str
    expected_references: tuple[tuple[str, str, str | None, int | None], ...] = ()
    expected_error: str = ""
    expected_native_calls: int = 0


@dataclass(frozen=True)
class NativeReferenceErrorTestCase:
    """Expanded SQL whose native error is located through its source map without Python."""

    description: str
    sql: str
    contents: str
    source_map: SqlReferenceSourceMap | None
    expected_message: str


@dataclass(frozen=True)
class ReferenceScanBoundTestCase:
    """A worst-case SQL shape the native scan must finish within a strict time limit."""

    description: str
    sql: str
    expected_outcome: int | str
    expected_maximum_seconds: float
