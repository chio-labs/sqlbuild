"""Copy a project and run every differential command under one engine in fresh processes."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from scripts.compiler_differential._helpers.running.records import read_analysis_records
from scripts.compiler_differential.constants import (
    ANALYSIS_RECORD_ENV_VAR,
    CAPTURES_DIRECTORY,
    COMMAND_TIMEOUT_SECONDS,
    COMPILED_DIRECTORY,
    DAG_FILE,
    ENGINE_ENV_VAR,
    EXCLUDED_ENVIRONMENT_KEYS,
    EXCLUDED_ENVIRONMENT_PREFIX,
    GENERATOR_ENVIRONMENT,
    MANIFEST_FILE,
    PROJECT_DIRECTORY,
    RECORDS_DIRECTORY,
    SQB_ENTRY,
    STAGE_CAPTURE_ENV_VAR,
)
from scripts.compiler_differential.models import (
    CommandOutcome,
    CorpusProject,
    DifferentialCommand,
    DifferentialOptions,
    EngineRun,
)

_COPY_IGNORED: tuple[str, ...] = (
    "target",
    "logs",
    "__pycache__",
    ".sqlbuild",
    "*.duckdb",
    "*.duckdb.wal",
)


def run_engine(
    *,
    project: CorpusProject,
    source_dir: Path,
    case_dir: Path,
    engine: str,
    side: str,
    options: DifferentialOptions,
) -> EngineRun:
    """Run the project's commands under one engine in a fresh copy, keeping captures on disk."""

    workspace: Path = case_dir / PROJECT_DIRECTORY
    shutil.rmtree(workspace, ignore_errors=True)
    _ = shutil.copytree(source_dir, workspace, ignore=shutil.ignore_patterns(*_COPY_IGNORED))
    project_dir: Path = (
        workspace
        if project.project_subdirectory is None
        else workspace / project.project_subdirectory
    )
    capture_root: Path = case_dir / f"{side}-{engine}-{CAPTURES_DIRECTORY}"
    shutil.rmtree(capture_root, ignore_errors=True)
    record_root: Path = case_dir / f"{side}-{engine}-{RECORDS_DIRECTORY}"
    shutil.rmtree(record_root, ignore_errors=True)
    outcomes: list[CommandOutcome] = []
    for index, command in enumerate(project.commands):
        capture_dir: Path | None = (
            capture_root / f"{index}-{command.label}" if options.stage_captures else None
        )
        record_dir: Path | None = (
            record_root / f"{index}-{command.label}" if options.analysis_records else None
        )
        outcomes.append(
            _run_command(
                command=command,
                project_dir=project_dir,
                environment={
                    **_command_environment(
                        engine=engine,
                        options=options,
                        capture_dir=capture_dir,
                        record_dir=record_dir,
                    ),
                    **dict(command.environment),
                },
                python=options.python,
            )
        )
    run: EngineRun = EngineRun(
        engine=engine,
        outcomes=tuple(outcomes),
        compiled=_compiled_tree(project_dir / COMPILED_DIRECTORY),
        manifest=_optional_text(project_dir / MANIFEST_FILE),
        dag=_optional_text(project_dir / DAG_FILE),
        captures=_captures(capture_root),
        records=read_analysis_records(record_root) if options.analysis_records else None,
    )
    retained: Path = case_dir / engine
    shutil.rmtree(retained, ignore_errors=True)
    _ = workspace.rename(retained)
    return run


def harness_environment() -> dict[str, str]:
    """Return this environment without engine, capture or dbt settings, plus generator vars."""

    return {
        **{
            key: value
            for key, value in os.environ.items()
            if key not in EXCLUDED_ENVIRONMENT_KEYS
            and not key.startswith(EXCLUDED_ENVIRONMENT_PREFIX)
        },
        **GENERATOR_ENVIRONMENT,
    }


def _command_environment(
    *,
    engine: str,
    options: DifferentialOptions,
    capture_dir: Path | None,
    record_dir: Path | None,
) -> dict[str, str]:
    environment: dict[str, str] = {
        **harness_environment(),
        ENGINE_ENV_VAR: engine,
        **options.engine_environment.get(engine, {}),
    }
    if capture_dir is not None:
        environment[STAGE_CAPTURE_ENV_VAR] = str(capture_dir)
    if record_dir is not None:
        environment[ANALYSIS_RECORD_ENV_VAR] = str(record_dir)
    return environment


def _run_command(
    *, command: DifferentialCommand, project_dir: Path, environment: dict[str, str], python: Path
) -> CommandOutcome:
    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            [str(python), "-c", SQB_ENTRY, "--no-color", *command.arguments],
            cwd=project_dir,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        return CommandOutcome(
            label=command.label,
            exit_code=-1,
            stdout=_timeout_text(error.stdout),
            stderr=_timeout_text(error.stderr),
            timed_out=True,
        )
    return CommandOutcome(
        label=command.label,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _timeout_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else value.decode("utf-8", "surrogateescape")


def _compiled_tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _optional_text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8", errors="surrogateescape") if path.is_file() else None


def _captures(root: Path) -> dict[str, dict[str, Path]]:
    captures: dict[str, dict[str, Path]] = {}
    for command_dir in sorted(root.iterdir()) if root.is_dir() else ():
        captures[command_dir.name] = {
            capture.name: capture for capture in sorted(command_dir.iterdir()) if capture.is_file()
        }
    return captures
