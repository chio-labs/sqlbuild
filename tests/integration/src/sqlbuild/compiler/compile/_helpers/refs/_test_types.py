from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import SqlReferenceSourceMap
from sqlbuild.compiler.frontier.types import CompilerEngine


@dataclass(frozen=True)
class CraftedReferenceParityTestCase:
    """One SQL text whose native extraction must equal Python's under every lexical syntax."""

    description: str
    sql: str
    expected_rejected: int = 0
    expected_failed: int = 0


@dataclass(frozen=True)
class GeneratedReferenceParityTestCase:
    """Seeded reference SQL compared with Python, with minimum coverage of each outcome."""

    description: str
    syntax: str
    seed: int
    count: int
    expected_minimum_extracted: int
    expected_minimum_failed: int
    expected_minimum_table_functions: int
    expected_minimum_rejected: int
    expected_maximum_deferred: int


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
    expected_bridge_independent: bool


@dataclass(frozen=True)
class ReferenceDiagnosticParityTestCase:
    """Generated authored files whose rejected calls both engines must report identically."""

    description: str
    syntax: str
    seed: int
    count: int
    expected_minimum_located: int
    expected_minimum_located_errors: int


@dataclass(frozen=True)
class ReferenceScanBoundTestCase:
    """A worst-case SQL shape the native scan must finish within a strict time limit."""

    description: str
    sql: str
    expected_outcome: int | str
    expected_maximum_seconds: float
