"""Public entry for storing a full compile so an unchanged rerun can replay it."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.compile_reuse._helpers.store import write_compile_entry
from sqlbuild.cli.compile_reuse.classes.compile_artifact_writes import CompileArtifactWrites
from sqlbuild.cli.compile_reuse.classes.recorded_compile_output import RecordedCompileOutput
from sqlbuild.cli.compile_reuse.models import CompileRenderReuse, CompileReuseAttempt
from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads


def write_reusable_compile(
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
    render_reuse: CompileRenderReuse | None = None,
) -> None:
    """Store a reusable full compile, or drop the stored one when it cannot be reused."""

    write_compile_entry(
        attempt=attempt,
        output=output,
        exit_code=exit_code,
        input_reads=input_reads,
        artifact_writes=artifact_writes,
        compile_cache_enabled=compile_cache_enabled,
        artifacts_written=artifacts_written,
        dag_artifact_path=dag_artifact_path,
        json_output=json_output,
        render_reuse=render_reuse,
    )
