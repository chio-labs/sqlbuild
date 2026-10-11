"""Check, replay and record whole-project reuse through the native store."""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild._native import NativeReuseAttempt
from sqlbuild.cli.compile_reuse._helpers.provider_settings import provider_settings_inputs
from sqlbuild.cli.compile_reuse._helpers.runtime_identity import (
    invocation_identity,
    redirected_output_files,
    runtime_identity,
)
from sqlbuild.cli.compile_reuse._helpers.timings import elapsed_ms, reuse_timings
from sqlbuild.cli.compile_reuse.classes.compile_artifact_writes import CompileArtifactWrites
from sqlbuild.cli.compile_reuse.classes.recorded_compile_output import RecordedCompileOutput
from sqlbuild.cli.compile_reuse.constants import (
    BYTES_PER_MEBIBYTE,
    COMPILED_DIRECTORY_NAME,
    EXCLUDED_DIRECTORIES,
    EXCLUDED_ROOT_DIRECTORIES,
    MILLISECONDS_PER_SECOND,
    MISSING_ENVIRONMENT_VALUE,
    MISSING_FILE_DIGEST,
    MISSING_PATH_MTIME_NS,
    NATIVE_REUSE_DIRECTORY_NAME,
    PRESENCE_ONLY_FILE_SUFFIXES,
    PROJECT_CONFIG_FILENAMES,
    PROJECT_ROOT_PATH_MTIME_NS,
    RACY_WINDOW_NS,
    RETIRED_REUSE_DIRECTORY_NAME,
    REUSE_DISABLE_ENV_VAR,
    REUSE_DISABLE_VALUE,
    REUSE_HIT_MESSAGE,
    REUSE_LOGGER_NAME,
    REUSE_MAX_ENTRY_BYTES,
    REUSE_MAX_STORED_ENTRIES,
    REUSE_STORE_DONE_MESSAGE,
    REUSE_STORE_NOTICE_BYTES,
    REUSE_STORE_NOTICE_PATHS,
    REUSE_STORE_SKIPPED_MESSAGE,
    REUSE_STORE_START_MESSAGE,
    TARGET_DIRECTORY_NAME,
    TOTAL_TIMING,
    TRACKED_ENVIRONMENT_PREFIXES,
    UNTRACKED_ENVIRONMENT_NAMES,
)
from sqlbuild.cli.compile_reuse.models import (
    CompileReuseAttempt,
    CompileReuseRequest,
    SettingsInputsResult,
)
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome
from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads
from sqlbuild.compiler.compile.constants import (
    COMPILE_CACHE_DISABLE_ENV_VAR,
    COMPILE_CACHE_DISABLE_VALUE,
)
from sqlbuild.compiler.frontier.main.compiler_cache_directory import compiler_cache_directory
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.macro_bridge.main.macro_store_module_paths import (
    macro_store_module_paths,
)
from sqlbuild.presentation.main.supports_color import supports_color

_LOGGER: logging.Logger = logging.getLogger(REUSE_LOGGER_NAME)
_OUTCOMES: dict[str, CompileReuseOutcome] = {
    outcome.value: outcome for outcome in CompileReuseOutcome
}
_STORED: str = "stored"
_SKIPPED: str = "skipped"


def native_attempt(
    *, request: CompileReuseRequest, project_dir: str, started: float
) -> CompileReuseAttempt:
    """Check reuse natively, replaying on a hit."""

    attempt: NativeReuseAttempt = _native.check_compile_reuse(
        {
            "project_dir": project_dir,
            "store_directory": compiler_cache_directory(Path(project_dir))
            / NATIVE_REUSE_DIRECTORY_NAME,
            "selected_target": request.selected_target,
            "invocation": invocation_identity(
                request=request,
                project_dir=project_dir,
                use_color=(not request.no_color) and supports_color(),
            ),
            "runtime": runtime_identity(),
            "search_path": list(sys.path),
            "bypass_requested": request.no_cache
            or request.manifest
            or request.profiling
            or request.debug,
            "json_output": request.json_output,
            "rules": reuse_rules(),
        }
    )
    outcome: CompileReuseOutcome = _OUTCOMES[attempt.outcome()]
    base: CompileReuseAttempt = CompileReuseAttempt(
        outcome=outcome, project_dir=Path(project_dir), started=started
    )
    if outcome is CompileReuseOutcome.BYPASS:
        return base
    report_native_answer(
        stage=NativeStage.COMPILE_OUTPUTS,
        kind="reuse_snapshot_paths",
        units=attempt.snapshot_paths(),
    )
    report_native_answer(
        stage=NativeStage.COMPILE_OUTPUTS,
        kind="reuse_digested_files",
        units=attempt.digested_files(),
    )
    missed: CompileReuseAttempt = replace(
        base,
        outcome=CompileReuseOutcome.MISS,
        entry_path=Path(attempt.store_path()),
        native=attempt,
        check_ms=0 if attempt.replay_failed() else elapsed_ms(started=started),
    )
    if outcome is CompileReuseOutcome.HIT:
        return _replayed(attempt=attempt, missed=missed, started=started, json=request.json_output)
    return missed


def _replayed(
    *,
    attempt: NativeReuseAttempt,
    missed: CompileReuseAttempt,
    started: float,
    json: bool,
) -> CompileReuseAttempt:
    check_ms: int = elapsed_ms(started=started)
    timings: dict[str, int] = {
        **reuse_timings(outcome=CompileReuseOutcome.HIT, check_ms=check_ms),
        TOTAL_TIMING: elapsed_ms(started=started),
    }
    replay: tuple[str, list[str], int] | None = attempt.replay(
        list(timings.items()) if json else []
    )
    if replay is None:
        return replace(missed, check_ms=0)
    stdout, stderr_lines, exit_code = replay
    print(REUSE_HIT_MESSAGE.format(seconds=check_ms / MILLISECONDS_PER_SECOND), file=sys.stderr)
    for line in stderr_lines:
        print(line, file=sys.stderr)
    _ = sys.stdout.write(stdout)
    sys.stdout.flush()
    report_native_answer(stage=NativeStage.COMPILE_OUTPUTS, kind="reuse_replays")
    return replace(missed, outcome=CompileReuseOutcome.HIT, check_ms=check_ms, exit_code=exit_code)


def record_native(
    *,
    store_path: Path,
    native: NativeReuseAttempt,
    output: RecordedCompileOutput,
    exit_code: int,
    input_reads: CompileInputReads,
    artifact_writes: CompileArtifactWrites,
    compile_cache_enabled: bool,
    artifacts_written: bool,
    dag_artifact_path: Path | None,
    json_output: bool,
) -> None:
    """Store a reusable compile natively, or clear the slot when it cannot be reused."""

    try:
        _record(
            native=native,
            output=output,
            exit_code=exit_code,
            input_reads=input_reads,
            artifact_writes=artifact_writes,
            compile_cache_enabled=compile_cache_enabled,
            artifacts_written=artifacts_written,
            dag_artifact_path=dag_artifact_path,
            json_output=json_output,
        )
    except Exception:
        _LOGGER.debug("Compile reuse did not store this compile", exc_info=True)
        with contextlib.suppress(OSError):
            store_path.unlink(missing_ok=True)


def _record(
    *,
    native: NativeReuseAttempt,
    output: RecordedCompileOutput,
    exit_code: int,
    input_reads: CompileInputReads,
    artifact_writes: CompileArtifactWrites,
    compile_cache_enabled: bool,
    artifacts_written: bool,
    dag_artifact_path: Path | None,
    json_output: bool,
) -> None:
    settings: SettingsInputsResult = provider_settings_inputs(
        settings_classes=input_reads.settings_classes
    )
    if settings.unsupported_reason is not None:
        _LOGGER.debug("Compile reuse is off for this project: %s", settings.unsupported_reason)
    eligible: bool = (
        output.stdout is not None
        and compile_cache_enabled
        and not input_reads.read_run_id
        and settings.unsupported_reason is None
    )
    notice_started: float | None = _start_notice(native=native) if eligible else None
    outcome, digested_files = native.record(
        {
            "stdout": output.stdout,
            "stderr_lines": list(output.stderr_lines),
            "exit_code": exit_code,
            "compile_cache_enabled": compile_cache_enabled,
            "read_run_id": input_reads.read_run_id,
            "settings_inputs": None
            if settings.unsupported_reason is not None
            else [
                (
                    item.case_sensitive,
                    list(item.names),
                    list(item.prefixes),
                    list(item.env_files),
                    list(item.secrets_dirs),
                )
                for item in settings.inputs
            ],
            "template_environment_names": list(input_reads.environment_names),
            "module_paths": _module_paths(),
            "artifacts": {
                path: (artifact.digest, artifact.size, artifact.mtime_ns)
                for path, artifact in artifact_writes.artifacts.items()
            },
            "artifacts_written": artifacts_written,
            "dag_path": None if dag_artifact_path is None else os.path.abspath(dag_artifact_path),
            "json_output": json_output,
            "rules": reuse_rules(),
        }
    )
    report_native_answer(
        stage=NativeStage.COMPILE_OUTPUTS, kind="reuse_digested_files", units=digested_files
    )
    if outcome == _STORED:
        report_native_answer(stage=NativeStage.COMPILE_OUTPUTS, kind="reuse_records")
    _finish_notice(
        started=notice_started,
        message=REUSE_STORE_SKIPPED_MESSAGE if outcome == _SKIPPED else REUSE_STORE_DONE_MESSAGE,
    )


def reuse_rules() -> dict[str, object]:
    """The reuse constants the native check and record share with the Python implementation."""

    return {
        "excluded": sorted(EXCLUDED_DIRECTORIES),
        "excluded_root": sorted(EXCLUDED_ROOT_DIRECTORIES),
        "presence_suffixes": list(PRESENCE_ONLY_FILE_SUFFIXES),
        "output_files": redirected_output_files(),
        "tracked_prefixes": list(TRACKED_ENVIRONMENT_PREFIXES),
        "untracked_names": sorted(UNTRACKED_ENVIRONMENT_NAMES),
        "disabling_variables": [
            (COMPILE_CACHE_DISABLE_ENV_VAR, COMPILE_CACHE_DISABLE_VALUE),
            (REUSE_DISABLE_ENV_VAR, REUSE_DISABLE_VALUE),
        ],
        "config_filenames": list(PROJECT_CONFIG_FILENAMES),
        "racy_window_ns": RACY_WINDOW_NS,
        "max_stored_entries": REUSE_MAX_STORED_ENTRIES,
        "max_entry_bytes": REUSE_MAX_ENTRY_BYTES,
        "missing_environment_value": MISSING_ENVIRONMENT_VALUE,
        "missing_file_digest": MISSING_FILE_DIGEST,
        "missing_path_mtime_ns": MISSING_PATH_MTIME_NS,
        "project_root_path_mtime_ns": PROJECT_ROOT_PATH_MTIME_NS,
        "compiled_root": os.path.join(TARGET_DIRECTORY_NAME, COMPILED_DIRECTORY_NAME),
        "retired_directories": [RETIRED_REUSE_DIRECTORY_NAME],
    }


def _module_paths() -> list[str]:
    """Loaded module files, then the macro store's extra module paths, as Python lists them."""

    module_files: list[object] = [
        getattr(module, "__file__", None) for module in tuple(sys.modules.values())
    ]
    return [
        path
        for path in (*module_files, *sorted(macro_store_module_paths()))
        if isinstance(path, str)
    ]


def _start_notice(*, native: NativeReuseAttempt) -> float | None:
    pending_bytes: int = native.pending_digest_bytes()
    paths: int = native.snapshot_paths()
    if pending_bytes < REUSE_STORE_NOTICE_BYTES and paths < REUSE_STORE_NOTICE_PATHS:
        return None
    print(
        REUSE_STORE_START_MESSAGE.format(paths=paths, mebibytes=pending_bytes / BYTES_PER_MEBIBYTE),
        file=sys.stderr,
    )
    return time.monotonic()


def _finish_notice(*, started: float | None, message: str) -> None:
    if started is not None:
        print(message.format(seconds=time.monotonic() - started), file=sys.stderr)
