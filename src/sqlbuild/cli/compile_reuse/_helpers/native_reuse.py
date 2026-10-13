"""Check, replay and record whole-project reuse through the native store."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild._native import NativeReuseAttempt
from sqlbuild.cli.compile_reuse._helpers.runtime_identity import (
    invocation_identity,
    redirected_output_files,
    runtime_identity,
)
from sqlbuild.cli.compile_reuse._helpers.timings import elapsed_ms, reuse_timings
from sqlbuild.cli.compile_reuse.constants import (
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
    TARGET_DIRECTORY_NAME,
    TOTAL_TIMING,
    TRACKED_ENVIRONMENT_PREFIXES,
    UNTRACKED_ENVIRONMENT_NAMES,
)
from sqlbuild.cli.compile_reuse.models import (
    CompileReuseAttempt,
    CompileReuseRequest,
)
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome
from sqlbuild.compiler.compile.constants import (
    COMPILE_CACHE_DISABLE_ENV_VAR,
    COMPILE_CACHE_DISABLE_VALUE,
)
from sqlbuild.compiler.frontier.main.compiler_cache_directory import compiler_cache_directory
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
        outcome=outcome,
        project_dir=Path(project_dir),
        started=started,
        selected_target=request.selected_target,
        json_output=request.json_output,
    )
    if outcome is CompileReuseOutcome.BYPASS:
        return base
    _LOGGER.debug("Compile reuse check digested %d project files", attempt.digested_files())
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
    return replace(missed, outcome=CompileReuseOutcome.HIT, check_ms=check_ms, exit_code=exit_code)


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
