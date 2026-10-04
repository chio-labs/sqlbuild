"""Test-case models for the same-runner compile performance ratio guard."""

from dataclasses import dataclass

from scripts.compile_performance_ratio.models import CompileComparison


@dataclass(frozen=True)
class RatioFailuresTestCase:
    description: str
    comparisons: tuple[CompileComparison, ...]
    modes: tuple[str, ...]
    max_ratio: float
    expected_failures: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonMarkdownTestCase:
    description: str
    comparisons: tuple[CompileComparison, ...]
    failures: tuple[str, ...]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class OneModelEditTestCase:
    description: str
    model_files: dict[str, str]
    revisions: int
    expected_paths: tuple[str, ...]
    expected_files: dict[str, str]


@dataclass(frozen=True)
class OneModelEditErrorTestCase:
    description: str
    model_files: dict[str, str]
    expected_message: str
