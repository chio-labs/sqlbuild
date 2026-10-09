"""Test case types for the differential harness running helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from scripts.compiler_differential.models import (
    AnalysisRecords,
    ExpectedOutcome,
    ProjectComparison,
    RecordedRun,
)


@dataclass(frozen=True)
class EngineEnvironmentTestCase:
    """Repeated --engine-env values and the per-engine overrides they produce."""

    description: str
    values: tuple[str, ...]
    expected_environment: dict[str, dict[str, str]]


@dataclass(frozen=True)
class EngineEnvironmentErrorTestCase:
    """A malformed --engine-env value and the usage error it raises."""

    description: str
    value: str
    expected_message: str


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
    gate_failures: tuple[str, ...]
    expected_lines: tuple[str, ...]
    expected_absent: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisRecordsTestCase:
    """Record files two engine processes wrote and the report lines they must produce."""

    description: str
    files: dict[str, str]
    expected_wheel_sites: dict[tuple[str, str], int]
    expected_deferrals: dict[tuple[str, str], int]
    expected_fallbacks: dict[tuple[str, str], int]
    expected_lines: tuple[str, ...]


@dataclass(frozen=True)
class FallbackGateTestCase:
    """An allow-list file, what one run observed, and the problems the gate must report."""

    description: str
    allow_list: str
    observed: dict[tuple[str, str, str, str], dict[str, int]]
    run: RecordedRun
    expected_problems: list[str]


@dataclass(frozen=True)
class FallbackRecordsTestCase:
    """Per-engine records of one project and the allow-list entries they add up to."""

    description: str
    project: str
    records: tuple[AnalysisRecords, AnalysisRecords]
    expected_observed: dict[tuple[str, str, str, str], dict[str, int]]


@dataclass(frozen=True)
class FallbackRewriteTestCase:
    """An allow-list, a run that rewrites it, and the counts the rewritten list must hold."""

    description: str
    allow_list: str
    observed: dict[tuple[str, str, str, str], dict[str, int]]
    run: RecordedRun
    expected_counts: dict[tuple[str, str, str, str], dict[str, int]]
