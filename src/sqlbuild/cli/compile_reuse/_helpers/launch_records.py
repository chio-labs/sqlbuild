"""Leave the native `sqb` executable what it needs to serve the next unchanged compile itself."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from sqlbuild._native import NativeReuseAttempt
from sqlbuild.cli.compile_reuse._helpers.native_reuse import reuse_rules
from sqlbuild.cli.compile_reuse._helpers.startup_inputs import startup_inputs
from sqlbuild.cli.compile_reuse.constants import (
    COMPILE_COMMAND_NAME,
    COMPUTE_LOG_DIRECTORY_NAME,
    LAUNCH_RECORD_DIRECTORY,
    LAUNCH_RECORD_FORMAT,
    LAUNCH_RECORD_LIMIT,
    REUSE_BYPASS_TIMING,
    REUSE_CHECK_TIMING,
    REUSE_HIT_MESSAGE,
    REUSE_HIT_TIMING,
    REUSE_LOGGER_NAME,
    REUSE_MISS_TIMING,
    TOTAL_TIMING,
)
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt
from sqlbuild.cli.entry.main._launch_record_path import launch_record_path
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from sqlbuild.runtime.compute_logs.classes.text_tee import TextComputeLogTee
from sqlbuild.runtime.output_capture.constants import INVOCATION_CONTEXT_ENV

_LOGGER: logging.Logger = logging.getLogger(REUSE_LOGGER_NAME)
_SECONDS_FIELD: str = "{seconds:.1f}"
_OUTPUT_FILES_RULE: str = "output_files"


def write_launch_record(*, attempt: CompileReuseAttempt) -> None:
    """Record this reusable compile for `sqb` when nothing it cannot replay took part."""

    path: Path | None = launch_record_path()
    native: NativeReuseAttempt | None = attempt.native
    if path is None or native is None or not _replayable_natively():
        return
    directory: Path = attempt.project_dir.joinpath(*LAUNCH_RECORD_DIRECTORY)
    if path.parent.resolve() != directory.resolve():
        return
    try:
        _write(path=path, payload=_payload(attempt=attempt, native=native, key=path.stem))
        _prune(directory=directory)
    except OSError:
        _LOGGER.debug("Compile reuse did not leave a launch record", exc_info=True)


def _replayable_natively() -> bool:
    return INVOCATION_CONTEXT_ENV not in os.environ and not os.environ.get(
        ANALYSIS_RECORD_DIR_ENV_VAR
    )


def _payload(
    *, attempt: CompileReuseAttempt, native: NativeReuseAttempt, key: str
) -> dict[str, object]:
    invocation_digest, runtime, search_path = native.launch_identity()
    rules: dict[str, object] = {
        name: value for name, value in reuse_rules().items() if name != _OUTPUT_FILES_RULE
    }
    project_dir: Path = attempt.project_dir.resolve()
    prefix, suffix = REUSE_HIT_MESSAGE.split(_SECONDS_FIELD)
    return {
        "format": LAUNCH_RECORD_FORMAT,
        "key": key,
        "project_dir": str(attempt.project_dir),
        "store_path": native.store_path(),
        "invocation_digest": invocation_digest,
        "runtime": runtime,
        "search_path": search_path,
        "startup_inputs": startup_inputs(),
        "json_output": attempt.json_output,
        "rules": rules,
        "capture": {
            "root": str((project_dir / COMPUTE_LOG_DIRECTORY_NAME).resolve()),
            "command": COMPILE_COMMAND_NAME,
            "project_dir": str(project_dir),
            "target": attempt.selected_target,
        }
        if isinstance(sys.stdout, TextComputeLogTee)
        else None,
        "hit_message": [prefix, suffix],
        "timings": {
            "hit": REUSE_HIT_TIMING,
            "miss": REUSE_MISS_TIMING,
            "bypass": REUSE_BYPASS_TIMING,
            "check": REUSE_CHECK_TIMING,
            "total": TOTAL_TIMING,
        },
    }


def _write(*, path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _ = temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)


def _prune(*, directory: Path) -> None:
    records: list[tuple[int, Path]] = [
        (entry.stat().st_mtime_ns, entry) for entry in directory.glob("*.json")
    ]
    records.sort(reverse=True)
    for _, stale in records[LAUNCH_RECORD_LIMIT:]:
        with contextlib.suppress(OSError):
            stale.unlink()
