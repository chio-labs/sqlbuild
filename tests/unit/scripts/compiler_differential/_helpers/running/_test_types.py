"""Test case types for the differential harness running helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from scripts.compiler_differential.models import ExpectedOutcome, ProjectComparison


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
    expected_lines: tuple[str, ...]
    expected_absent: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisRecordsTestCase:
    """Record files two engine processes wrote and the report lines they must produce."""

    description: str
    files: dict[str, str]
    expected_wheel_sites: dict[tuple[str, str], int]
    expected_deferrals: dict[tuple[str, str], int]
    expected_lines: tuple[str, ...]


@dataclass(frozen=True)
class FailureEvidenceTestCase:
    """Per-engine warm-compile stderr and the evidence files a comparison keeps."""

    description: str
    stderr_by_engine: dict[str, str]
    expected_files: tuple[str, ...]
    expected_evidence_engines: tuple[str, ...]
