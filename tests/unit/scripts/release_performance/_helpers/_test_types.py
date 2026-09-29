"""Test-case models for the release performance comparison."""

from dataclasses import dataclass

from scripts.release_performance.models import CommandComparison, SkippedCommand


@dataclass(frozen=True)
class MetricVerdictTestCase:
    description: str
    comparison: CommandComparison
    expected_regressed: tuple[bool, bool, bool]


@dataclass(frozen=True)
class SkipReasonTestCase:
    description: str
    minimum_version: str | None
    baseline_version: str
    candidate_version: str
    expected_reason: str | None


@dataclass(frozen=True)
class ComparisonMarkdownTestCase:
    description: str
    commands: tuple[CommandComparison, ...]
    skipped: tuple[SkippedCommand, ...]
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PreviousVersionTestCase:
    description: str
    candidate: str
    versions: tuple[str, ...]
    expected_version: str | None


@dataclass(frozen=True)
class ReleaseVersionsTestCase:
    description: str
    files: tuple[dict[str, object], ...]
    expected_versions: tuple[str, ...]


@dataclass(frozen=True)
class CompatibleWheelsTestCase:
    description: str
    machine: str
    system: str
    expected_filenames: tuple[str, ...]


@dataclass(frozen=True)
class ChooseBaselineTestCase:
    description: str
    candidate: str
    files: tuple[dict[str, object], ...]
    tags: tuple[str, ...]
    expected_baseline: str | None
