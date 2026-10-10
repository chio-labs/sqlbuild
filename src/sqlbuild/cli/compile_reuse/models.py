"""Compile reuse requests, provider settings inputs, and per-invocation reuse state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild._native import NativeReuseAttempt
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome


@dataclass(frozen=True)
class CompileReuseRequest:
    """The compile command choices that decide whether and how a compile is reused."""

    project_dir: Path | None
    selected_target: str | None
    json_output: bool
    no_color: bool
    manifest: bool
    dag_path: str | None
    defer_to: str | None
    no_cache: bool
    no_sql_validation: bool
    lineage_mode: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    cli_vars: dict[str, object] | None
    profiling: bool
    debug: bool


@dataclass(frozen=True)
class SettingsEnvironmentInputs:
    """Where one provider settings class can read values outside the project files."""

    case_sensitive: bool
    names: tuple[str, ...]
    prefixes: tuple[str, ...]
    env_files: tuple[str, ...]
    secrets_dirs: tuple[str, ...]


@dataclass(frozen=True)
class SettingsInputsResult:
    """Enumerated provider settings inputs, or why they cannot be enumerated exactly."""

    inputs: tuple[SettingsEnvironmentInputs, ...]
    unsupported_reason: str | None = None


@dataclass(frozen=True)
class RecordedArtifact:
    """What one compile wrote to an artifact: its content digest, or the stat it kept."""

    digest: str | None
    size: int | None = None
    mtime_ns: int | None = None


@dataclass(frozen=True)
class CompileReuseAttempt:
    """Result of checking for a reusable compile, carried into a full compile on a miss."""

    outcome: CompileReuseOutcome
    project_dir: Path
    started: float
    check_ms: int = 0
    exit_code: int | None = None
    entry_path: Path | None = None
    native: NativeReuseAttempt | None = field(default=None, compare=False, repr=False)
    """The natively checked attempt, recorded natively after a miss."""
