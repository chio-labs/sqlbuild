"""Record a completed full compile so an unchanged rerun can replay it."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.compile_reuse._helpers.native_reuse import record_native
from sqlbuild.cli.compile_reuse.classes.compile_artifact_writes import CompileArtifactWrites
from sqlbuild.cli.compile_reuse.classes.recorded_compile_output import RecordedCompileOutput
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome
from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads


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

    if (
        attempt.outcome is not CompileReuseOutcome.MISS
        or attempt.entry_path is None
        or attempt.native is None
    ):
        return
    record_native(
        store_path=attempt.entry_path,
        native=attempt.native,
        output=output,
        exit_code=exit_code,
        input_reads=input_reads,
        artifact_writes=artifact_writes,
        compile_cache_enabled=compile_cache_enabled,
        artifacts_written=artifacts_written,
        dag_artifact_path=dag_artifact_path,
        json_output=json_output,
    )
