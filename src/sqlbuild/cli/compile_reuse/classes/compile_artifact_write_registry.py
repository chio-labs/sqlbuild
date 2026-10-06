"""Process-wide delivery of compile artifact writes to the active compile recorders."""

from __future__ import annotations

import hashlib
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlbuild.cli.compile_reuse.classes.compile_artifact_writes import CompileArtifactWrites
from sqlbuild.cli.compile_reuse.models import RecordedArtifact

if TYPE_CHECKING:
    from sqlbuild.cli.compile_reuse.classes.stored_artifacts import StoredArtifacts


class CompileArtifactWriteRegistry:
    """Deliver artifact writes from every thread, including background staging threads."""

    def __init__(self, *, digest_size: int) -> None:
        self._digest_size: int = digest_size
        self._lock: threading.Lock = threading.Lock()
        self._recorders: tuple[CompileArtifactWrites, ...] = ()
        self._stored: StoredArtifacts | None = None

    @contextmanager
    def recording(
        self, *, stored: StoredArtifacts | None = None
    ) -> Iterator[CompileArtifactWrites]:
        """Record artifact writes until the block exits, trusting unchanged stored artifacts."""

        recorder: CompileArtifactWrites = CompileArtifactWrites()
        with self._lock:
            self._recorders = (*self._recorders, recorder)
            if stored is not None:
                self._stored = stored
        try:
            yield recorder
        finally:
            with self._lock:
                self._recorders = tuple(item for item in self._recorders if item is not recorder)
                if stored is not None:
                    self._stored = None

    def written(self, *, path: str | os.PathLike[str], contents: bytes) -> bool:
        """Note the exact bytes an artifact holds; return whether it already holds them."""

        recorders: tuple[CompileArtifactWrites, ...] = self._recorders
        if not recorders:
            return False
        absolute_path: str = os.path.abspath(path)
        artifact: RecordedArtifact = RecordedArtifact(
            digest=hashlib.blake2b(contents, digest_size=self._digest_size).hexdigest()
        )
        for recorder in recorders:
            recorder.record(path=absolute_path, artifact=artifact)
        stored: StoredArtifacts | None = self._stored
        return stored is not None and stored.holds(path=absolute_path, digest=artifact.digest)

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
