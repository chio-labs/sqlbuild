"""Typed records for the planner differential."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class PlannerProject:
    """One project the mutation script runs on."""

    name: str
    source_dir: Path | None = None
    writer: Callable[[Path], None] | None = None


@dataclass(frozen=True)
class PlannerStep:
    """One mutation of a `role` model (candidate `index`), then plan and build with `arguments`."""

    name: str
    mutation: str | None = None
    role: str | None = None
    index: int = 0
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelFacts:
    """What the previous plan says about one model, for choosing step targets."""

    name: str
    relative_path: str
    materialization: str
    qualified_name: str
    cursor_column: str | None
    microbatch: bool


@dataclass(frozen=True)
class ModelFile:
    """A SQL model file's MODEL header (possibly empty) and its single query."""

    header: str
    query: str


@dataclass(frozen=True)
class StepContext:
    """Where a step runs and the models the previous plan reported."""

    project_dir: Path
    models: tuple[ModelFacts, ...]
    source_tables: tuple[str, ...]
    environment: dict[str, str]
    python: Path


@dataclass(frozen=True)
class MutationResult:
    """Whether a mutation applied, and a stable note describing what it changed."""

    applied: bool
    note: str


@dataclass(frozen=True)
class TextMasks:
    """Run-specific text to mask: path prefixes by their mask, and the run's date."""

    replacements: tuple[tuple[str, str], ...]
    today: date


@dataclass(frozen=True)
class CommandResult:
    """One sqb invocation's exit code and output."""

    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RunOptions:
    """Resolved harness settings."""

    work_dir: Path
    jobs: int
    python: Path
    mode: str
    baseline_dir: Path
    keep_work: bool
    steps: tuple[PlannerStep, ...]


@dataclass(frozen=True)
class ProjectDifference:
    """One artifact of one step that differs from the baseline, with a readable diff."""

    step: str
    artifact: str
    diff: str


@dataclass(frozen=True)
class ProjectResult:
    """A project's verdict against the baseline."""

    project: str
    seconds: float
    differences: tuple[ProjectDifference, ...]
    error: str | None = None
