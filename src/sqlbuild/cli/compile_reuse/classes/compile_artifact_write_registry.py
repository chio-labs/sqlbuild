"""Process-wide delivery of compile artifact writes to the active compile recorders."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import sqlbuild._native as _native
from sqlbuild.cli.compile_reuse.classes.compile_artifact_writes import CompileArtifactWrites
from sqlbuild.cli.compile_reuse.models import RecordedArtifact


class CompileArtifactWriteRegistry:
    """Deliver artifact writes from every thread, including background staging threads."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._recorders: tuple[CompileArtifactWrites, ...] = ()

    @contextmanager
    def recording(self) -> Iterator[CompileArtifactWrites]:
        """Record artifact writes until the block exits."""

        recorder: CompileArtifactWrites = CompileArtifactWrites()
        with self._lock:
            self._recorders = (*self._recorders, recorder)
        try:
            yield recorder
        finally:
            with self._lock:
                self._recorders = tuple(item for item in self._recorders if item is not recorder)

    def written(self, *, path: str | os.PathLike[str], contents: bytes) -> None:
        """Note the exact bytes an artifact holds after a write or an unchanged-file check."""

        recorders: tuple[CompileArtifactWrites, ...] = self._recorders
        if not recorders:
            return
        artifact: RecordedArtifact = RecordedArtifact(digest=_native.artifact_digest(contents))
        for recorder in recorders:
            recorder.record(path=os.path.abspath(path), artifact=artifact)

    def kept(self, *, path: str | os.PathLike[str], size: int, mtime_ns: int) -> None:
        """Note an earlier artifact kept as-is after its size and mtime were validated."""

        artifact: RecordedArtifact = RecordedArtifact(digest=None, size=size, mtime_ns=mtime_ns)
        for recorder in self._recorders:
            recorder.record(path=os.path.abspath(path), artifact=artifact)

    def moved(self, *, source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        """Note that one staged artifact was published at another path."""

        for recorder in self._recorders:
            recorder.move(source=os.path.abspath(source), destination=os.path.abspath(destination))

    def moved_tree(
        self, *, source: str | os.PathLike[str], destination: str | os.PathLike[str]
    ) -> None:
        """Note that a staged artifact directory was published at another directory."""

        for recorder in self._recorders:
            recorder.move_tree(
                source=os.path.abspath(source), destination=os.path.abspath(destination)
            )
