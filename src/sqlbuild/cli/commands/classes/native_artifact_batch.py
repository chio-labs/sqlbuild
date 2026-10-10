"""Queue compiled artifacts and write each group in one native call."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.cli.compile_reuse.constants import COMPILE_ARTIFACT_WRITES
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.profiling.main.record import record_compile_timing


class NativeArtifactBatch:
    """Compiled artifacts queued for the native writer, keeping unchanged files when asked."""

    def __init__(self, *, check_existing: bool) -> None:
        self.check_existing: bool = check_existing
        self._files: list[tuple[Path, bytes]] = []

    def queue(self, *, path: Path, contents: bytes) -> None:
        """Queue one artifact, noting the bytes it will hold for compile reuse."""

        COMPILE_ARTIFACT_WRITES.written(path=path, contents=contents)
        self._files.append((path, contents))

    def flush(self) -> None:
        """Write every queued artifact natively and empty the queue."""

        if not self._files:
            return
        with record_compile_timing("physical_write_ms"):
            written, unchanged = _native.write_compiled_artifacts(self._files, self.check_existing)
        self._files = []
        report_native_answer(
            stage=NativeStage.COMPILE_OUTPUTS, kind="artifact_files", units=written + unchanged
        )
