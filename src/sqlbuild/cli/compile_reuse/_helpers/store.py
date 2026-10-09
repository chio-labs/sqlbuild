"""Record a completed full compile so an unchanged rerun can replay it."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from sqlbuild.cli.compile_reuse._helpers.entry_file import remove_entry, write_entry
from sqlbuild.cli.compile_reuse._helpers.project_files import (
    pending_digest_bytes,
    snapshot_project_files,
    stored_project_files,
    with_missing_digests,
)
from sqlbuild.cli.compile_reuse._helpers.provider_settings import provider_settings_inputs
from sqlbuild.cli.compile_reuse._helpers.runtime_identity import (
    environment_digest,
    loaded_module_stamps,
    settings_inputs_digest,
    tracked_environment_names,
)
from sqlbuild.cli.compile_reuse._helpers.target_files import verified_target_files
from sqlbuild.cli.compile_reuse._helpers.timings import compile_timings_span
from sqlbuild.cli.compile_reuse.classes.compile_artifact_writes import CompileArtifactWrites
from sqlbuild.cli.compile_reuse.classes.recorded_compile_output import RecordedCompileOutput
from sqlbuild.cli.compile_reuse.constants import (
    BYTES_PER_MEBIBYTE,
    REUSE_LOGGER_NAME,
    REUSE_STORE_DONE_MESSAGE,
    REUSE_STORE_NOTICE_BYTES,
    REUSE_STORE_NOTICE_PATHS,
    REUSE_STORE_SKIPPED_MESSAGE,
    REUSE_STORE_START_MESSAGE,
)
from sqlbuild.cli.compile_reuse.models import (
    CompileReuseAttempt,
    SettingsInputsResult,
    StoredCompileInputs,
    StoredCompileOutput,
)
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome, FileStamp
from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads
from sqlbuild.compiler.macro_bridge.main.macro_store_module_paths import (
    macro_store_module_paths,
)

_LOGGER: logging.Logger = logging.getLogger(REUSE_LOGGER_NAME)


def write_compile_entry(
    *,
    attempt: CompileReuseAttempt,
    output: RecordedCompileOutput,
    exit_code: int,
    input_reads: CompileInputReads,
    artifact_writes: CompileArtifactWrites,
    compile_cache_enabled: bool,
    artifacts_written: bool,
    dag_artifact_path: Path | None,
    json_output: bool,
) -> None:
    """Store a reusable compile, or drop the stored one when this compile cannot be reused."""

    if attempt.outcome is not CompileReuseOutcome.MISS or attempt.entry_path is None:
        return
    try:
        _write_compile_entry(
            attempt=attempt,
            entry_path=attempt.entry_path,
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
        remove_entry(path=attempt.entry_path)


def _write_compile_entry(
    *,
    attempt: CompileReuseAttempt,
    entry_path: Path,
    output: RecordedCompileOutput,
    exit_code: int,
    input_reads: CompileInputReads,
    artifact_writes: CompileArtifactWrites,
    compile_cache_enabled: bool,
    artifacts_written: bool,
    dag_artifact_path: Path | None,
    json_output: bool,
) -> None:
    stdout: str | None = output.stdout
    settings: SettingsInputsResult = provider_settings_inputs(
        settings_classes=input_reads.settings_classes
    )
    if settings.unsupported_reason is not None:
        _LOGGER.debug("Compile reuse is off for this project: %s", settings.unsupported_reason)
    if (
        stdout is None
        or not compile_cache_enabled
        or input_reads.read_run_id
        or settings.unsupported_reason is not None
    ):
        remove_entry(path=entry_path)
        return
    project_dir: str = str(attempt.project_dir)
    notice_started: float | None = _start_notice(attempt=attempt)
    digests: dict[str, str] = with_missing_digests(
        project_dir=project_dir,
        snapshot=attempt.snapshot,
        digests=attempt.digests,
        paths=attempt.restamped,
        snapshot_ns=attempt.snapshot_ns,
    )
    target_files: dict[str, FileStamp] | None = (
        verified_target_files(
            project_dir=project_dir,
            dag_path=None if dag_artifact_path is None else os.path.abspath(dag_artifact_path),
            artifacts=artifact_writes.artifacts,
            written=artifacts_written,
            since_ns=attempt.snapshot_ns,
        )
        if snapshot_project_files(project_dir=project_dir) == attempt.snapshot
        else None
    )
    if target_files is None:
        remove_entry(path=entry_path)
        _finish_notice(started=notice_started, message=REUSE_STORE_SKIPPED_MESSAGE)
        return
    environment_names: tuple[str, ...] = tracked_environment_names(
        template_names=input_reads.environment_names
    )
    write_entry(
        path=entry_path,
        inputs=StoredCompileInputs(
            invocation_digest=attempt.invocation_digest,
            runtime=attempt.runtime,
            environment_names=environment_names,
            environment_digest=environment_digest(names=environment_names),
            search_path=attempt.search_path,
            modules=loaded_module_stamps(
                covered_paths=frozenset(
                    os.path.join(project_dir, relative_path) for relative_path in attempt.snapshot
                ),
                extra_paths=macro_store_module_paths(),
            ),
            project_files=stored_project_files(
                snapshot=attempt.snapshot, digests=digests, snapshot_ns=attempt.snapshot_ns
            ),
            target_files=target_files,
            target_tree=artifacts_written,
            settings_inputs=settings.inputs,
            settings_digest=settings_inputs_digest(inputs=settings.inputs),
        ),
        output=StoredCompileOutput(
            stderr_lines=output.stderr_lines,
            exit_code=exit_code,
            timings_span=compile_timings_span(stdout=stdout) if json_output else None,
            stdout_length=len(stdout),
            stdout_checksum=0,
            stdout_file="",
        ),
        stdout=stdout,
    )
    _finish_notice(started=notice_started, message=REUSE_STORE_DONE_MESSAGE)


def _start_notice(*, attempt: CompileReuseAttempt) -> float | None:
    pending_bytes: int = pending_digest_bytes(
        snapshot=attempt.snapshot, digests=attempt.digests, paths=attempt.restamped
    )
    if pending_bytes < REUSE_STORE_NOTICE_BYTES and len(attempt.snapshot) < (
        REUSE_STORE_NOTICE_PATHS
    ):
        return None
    print(
        REUSE_STORE_START_MESSAGE.format(
            paths=len(attempt.snapshot), mebibytes=pending_bytes / BYTES_PER_MEBIBYTE
        ),
        file=sys.stderr,
    )
    return time.monotonic()


def _finish_notice(*, started: float | None, message: str) -> None:
    if started is not None:
        print(message.format(seconds=time.monotonic() - started), file=sys.stderr)
