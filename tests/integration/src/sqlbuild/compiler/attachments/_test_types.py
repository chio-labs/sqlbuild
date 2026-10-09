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
    expected_minimum_exact_errors: int


@dataclass(frozen=True)
class AttachedAuditParityTestCase:
    """Seeded attached audits rendered natively and by Python's attachment helpers."""

    description: str
    seed: int
    count: int
    expected_minimum_native: int
    expected_minimum_native_errors: int
    expected_minimum_deferred: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class AttachmentProjectTestCase:
    """One project variant compiled to compile inputs by each engine."""

    description: str
    overrides: dict[str, str]
    expected_native_entries: frozenset[str]
    expected_outcome_fragment: str


@dataclass(frozen=True)
class ParameterParityTestCase:
    """Seeded SQL test bodies whose `@param` references each engine expands."""

    description: str
    seed: int
    count: int
    expected_minimum_expanded: int
    expected_minimum_python_errors: int
    expected_minimum_exact_errors: int


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
    expected_minimum_native_errors: int


@dataclass(frozen=True)
class TargetParityTestCase:
    """Seeded model test targets validated by each engine against known resources."""

    description: str
    seed: int
    count: int
    expected_minimum_valid: int
    expected_minimum_python_errors: int


@dataclass(frozen=True)
class FunctionHeaderParityTestCase:
    """Seeded SQL and Python function headers attached by each engine."""

    description: str
    seed: int
    count: int
    target_schema: str | None
    inherit_default_namespace: bool
    expected_minimum_attached: int
    expected_minimum_python_errors: int
    expected_minimum_exact_errors: int


@dataclass(frozen=True)
class BodyCallParityTestCase:
    """Seeded helper bodies whose call reading the native extractor shares with a Python scanner."""

    description: str
    seed: int
    count: int
    expected_minimum_calls: int
