"""Typed records for the compiler engine differential harness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scripts.compiler_differential.types import FallbackKey


@dataclass(frozen=True)
class DifferentialCommand:
    """One sqb invocation run identically under both engines, with extra environment values."""

    label: str
    arguments: tuple[str, ...]
    environment: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ExpectedOutcome:
    """Success, or failure whose first error is `error_code`, plus an optional expected warning."""

    error_code: str | None = None
    succeeding_commands: tuple[str, ...] = ()
    warning_code: str | None = None


@dataclass(frozen=True)
class CorpusProject:
    """One project compared across engines."""

    name: str
    commands: tuple[DifferentialCommand, ...]
    expected: ExpectedOutcome
    source_dir: Path | None = None
    writer: Callable[[Path], None] | None = None
    project_subdirectory: str | None = None
    seed_coverage: bool = False


@dataclass(frozen=True)
class CommandOutcome:
    """What one sqb invocation printed and returned."""

    label: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True)
class AnalysisRecords:
    """Wheel calls by `(site, api)`, deferrals by `(kind, site)`, fallbacks by `(site, kind)`."""

    wheel_sites: dict[tuple[str, str], int] = field(default_factory=dict)
    deferrals: dict[tuple[str, str], int] = field(default_factory=dict)
    fallbacks: dict[tuple[str, str], int] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineRun:
    """Everything one engine produced for one corpus project."""

    engine: str
    outcomes: tuple[CommandOutcome, ...]
    compiled: dict[str, bytes]
    manifest: str | None
    dag: str | None
    captures: dict[str, dict[str, Path]] = field(default_factory=dict)
    records: AnalysisRecords | None = None


@dataclass(frozen=True)
class Divergence:
    """Where two values first differ, with short previews of both sides."""

    location: str
    left: str
    right: str


@dataclass(frozen=True)
class Difference:
    """The first observed divergence in one compared artifact."""

    project: str
    artifact: str
    location: str
    left: str
    right: str
    labels: tuple[str, str] | None = None


@dataclass(frozen=True)
class ProjectComparison:
    """All differences found for one corpus project."""

    project: str
    differences: tuple[Difference, ...]
    seconds: float
    discovered_kinds: frozenset[str] = frozenset()
    rendered_kinds: frozenset[str] = frozenset()
    analysed_kinds: frozenset[str] = frozenset()
    records: tuple[AnalysisRecords | None, AnalysisRecords | None] | None = None


@dataclass(frozen=True)
class DifferentialOptions:
    """Resolved harness settings."""

    engines: tuple[str, str]
    work_dir: Path
    jobs: int
    stage_captures: bool
    python: Path
    engine_environment: dict[str, dict[str, str]]
    require_discovery_coverage: bool = False
    require_render_coverage: bool = False
    require_analysis_coverage: bool = False
    analysis_records: bool = False
    golden_mode: str | None = None
    golden_dir: Path | None = None


@dataclass(frozen=True)
class WritableProject:
    """Project files that can be written below a fresh directory."""

    files: dict[str, str]

    def write(self, project_dir: Path) -> None:
        """Write every UTF-8 file, creating parent directories."""

        for relative_path, contents in sorted(self.files.items()):
            path: Path = project_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            _ = path.write_text(contents, encoding="utf-8", newline="\n")


@dataclass(frozen=True)
class GeneratedProject(WritableProject):
    """A deterministic random project and the error it was generated to produce, if any."""

    seed: int
    expected_error_code: str | None
    features: tuple[str, ...]
    succeeding_commands: tuple[str, ...] = ()
    extra_commands: tuple[DifferentialCommand, ...] = ()


@dataclass(frozen=True)
class FailureCase(WritableProject):
    """One minimal project that must fail compile with one diagnostic code."""

    name: str
    expected_code: str
    expected_warning_code: str | None = None
    expected_message: str | None = None
    expected_help: str | None = None
    expected_notes: tuple[str, ...] = ()
    expected_location: tuple[int, int] | None = None
    expected_codes: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ModelPlan:
    """One generated SQL model and the relations it reads."""

    name: str
    domain: str
    layer: str
    inputs: tuple[str, ...]
    description: str

    @property
    def folder(self) -> str:
        """Return the model's folder relative to the project root."""

        return f"models/{self.domain}/{self.layer}"


@dataclass(frozen=True)
class DeclarationPlan:
    """One generated enum, constant, macro, or named hook and the models that use it."""

    kind: str
    name: str
    consumers: tuple[ModelPlan, ...]
    body: str = ""
    private: bool = False


@dataclass(frozen=True)
class EmittedCodes:
    """The error and warning codes one compile reported, in report order."""

    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    first_error_message: str | None = None
    first_error_help: str | None = None
    first_error_notes: tuple[str, ...] = ()
    first_error_location: tuple[int, int] | None = None
    codes: tuple[str, ...] = ()

    @property
    def first_error(self) -> str | None:
        """Return the first reported error code, if any."""

        return self.errors[0] if self.errors else None


@dataclass(frozen=True)
class RecordedRun:
    """The engines, corpora and seed range one harness run covered."""

    engines: tuple[str, ...]
    corpora: tuple[str, ...]
    seed_start: int
    seeds: int


@dataclass(frozen=True)
class AllowList:
    """Allowed counts by `(engine, stage, site, kind)` and corpus, and the seeds they hold for."""

    seed_start: int
    seeds: int
    counts: dict[FallbackKey, dict[str, int]]
    max_counts: dict[FallbackKey, dict[str, int]]


@dataclass(frozen=True)
class FallbackGateRequest:
    """One run's fallback gate: check or rewrite `allow_list` from what the engines recorded."""

    mode: str
    allow_list: Path
    run: RecordedRun
