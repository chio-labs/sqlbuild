"""Test case types for the differential harness running helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from scripts.compiler_differential.models import (
    ExpectedOutcome,
    ProjectComparison,
)


@dataclass(frozen=True)
class ExpectedOutcomeTestCase:
    """One --expect value and the outcome it parses to."""

    description: str
    value: str
    expected_outcome: ExpectedOutcome


@dataclass(frozen=True)
class ExpectedOutcomeErrorTestCase:
    """One malformed --expect value."""

    description: str
    value: str
    expected_message: str


@dataclass(frozen=True)
class CoverageReportTestCase:
    """Covered kinds and the coverage report lines the harness must print."""

    description: str
    formatter: Callable[..., str]
    covered: frozenset[str]
    required: tuple[str, ...]
    expected_lines: tuple[str, ...]


@dataclass(frozen=True)
class SummaryTestCase:
    """Project results, missing required coverage, and the summary the harness must print."""

    description: str
    comparisons: list[ProjectComparison]
    missing_coverage: dict[str, tuple[str, ...]]
    expected_lines: tuple[str, ...]
    expected_absent: tuple[str, ...]


@dataclass(frozen=True)
class FailureEvidenceTestCase:
    """A warm compile's exit code and the evidence files a failing project keeps."""

    description: str
    exit_code: int
    expected_files: tuple[str, ...]
