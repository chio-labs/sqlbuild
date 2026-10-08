from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


@dataclass(frozen=True)
class AuthoredSqlParityTestCase:
    """Seeded authored SQL expanded by the Python engine and by the preview engine."""

    description: str
    seed: int
    count: int
    generate: Callable[[random.Random], str]
    expected_minimum_expanded: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class AttachedAuditParityTestCase:
    """Seeded attached audits rendered natively and by Python's attachment helpers."""

    description: str
    seed: int
    count: int
    expected_minimum_native: int
    expected_minimum_deferred: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class AttachmentProjectTestCase:
    """One project variant compiled to compile inputs by each engine."""

    description: str
    expected_preview_entries: frozenset[str]


@dataclass(frozen=True)
class CursorIntrinsicParityTestCase:
    """Seeded SQL checked for cursor intrinsics natively and by Python."""

    description: str
    seed: int
    count: int
    expected_minimum_free: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class ParameterParityTestCase:
    """Seeded SQL test bodies whose `@param` references each engine expands."""

    description: str
    seed: int
    count: int
    expected_minimum_expanded: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class OmittedSelectParityTestCase:
    """Seeded test bodies completed with an omitted `SELECT 1` under one lexical syntax."""

    description: str
    seed: int
    count: int
    syntax: SqlLexicalSyntax
    expected_minimum_completed: int


@dataclass(frozen=True)
class RawDirectLogicParityTestCase:
    """Seeded unexpanded direct-logic test bodies extracted natively and by Python."""

    description: str
    seed: int
    count: int
    expected_minimum_extracted: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class ScenarioParityTestCase:
    """Seeded scenario bodies extracted by each engine under one lexical syntax."""

    description: str
    seed: int
    count: int
    syntax: SqlLexicalSyntax
    expected_minimum_extracted: int
    expected_minimum_native: int
    expected_minimum_python_errors: int
