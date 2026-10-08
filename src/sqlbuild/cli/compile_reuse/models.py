"""Compile reuse requests, stored compile results, and per-invocation reuse state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome, FileStamp


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
class StoredProjectFile:
    """One project path recorded before the stored compile ran."""

    stamp: FileStamp
    digest: str | None
    racy: bool


@dataclass(frozen=True)
class StoredCompileInputs:
    """Every compile input identity recorded with one stored compile result."""

    invocation_digest: str
    runtime: dict[str, str]
    environment_names: tuple[str, ...]
    environment_digest: str
    search_path: tuple[tuple[str, int], ...]
    modules: tuple[tuple[str, int, int], ...]
    project_files: dict[str, StoredProjectFile]
    target_files: dict[str, FileStamp]
    target_tree: bool
    settings_inputs: tuple[SettingsEnvironmentInputs, ...]
    settings_digest: str


@dataclass(frozen=True)
class StoredCompileOutput:
    """The command output of one stored compile, in emission order."""

    stderr_lines: tuple[str, ...]
    exit_code: int
    timings_span: tuple[int, int] | None
    stdout_length: int
    stdout_checksum: int
    stdout_file: str


@dataclass(frozen=True)
class StoredCompileHeader:
    """Inputs and output description read without loading the stored stdout."""

    inputs: StoredCompileInputs
    output: StoredCompileOutput


@dataclass(frozen=True)
class ProjectFilesComparison:
    """Whether project files are unchanged, with digests verified while comparing."""

    unchanged: bool
    verified: dict[str, str]


@dataclass(frozen=True)
class CompileReuseAttempt:
    """Result of checking for a reusable compile, carried into a full compile on a miss."""

    outcome: CompileReuseOutcome
    project_dir: Path
    started: float
    check_ms: int = 0
    exit_code: int | None = None
    entry_path: Path | None = None
    invocation_digest: str = ""
    runtime: dict[str, str] = field(default_factory=dict)
    search_path: tuple[tuple[str, int], ...] = ()
    snapshot: dict[str, FileStamp] = field(default_factory=dict)
    snapshot_ns: int = 0
    digests: dict[str, str] = field(default_factory=dict)
    restamped: frozenset[str] = frozenset()
