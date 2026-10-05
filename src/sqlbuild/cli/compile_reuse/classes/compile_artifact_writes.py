"""Artifacts one compile wrote or kept, keyed by absolute path."""

from __future__ import annotations

import os
import threading

from sqlbuild.cli.compile_reuse.models import RecordedArtifact


class CompileArtifactWrites:
    """Record what one compile left in each artifact path, following staged moves."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._artifacts: dict[str, RecordedArtifact] = {}

    def record(self, *, path: str, artifact: RecordedArtifact) -> None:
        """Record the artifact this compile left at one path."""

        with self._lock:
            self._artifacts[path] = artifact

    def move(self, *, source: str, destination: str) -> None:
        """Follow one staged artifact to its published path."""

        with self._lock:
            artifact: RecordedArtifact | None = self._artifacts.pop(source, None)
            if artifact is not None:
                self._artifacts[destination] = artifact

    def move_tree(self, *, source: str, destination: str) -> None:
        """Follow every staged artifact under one directory to its published directory."""

        prefix: str = source + os.sep
        with self._lock:
            moved: dict[str, RecordedArtifact] = {
                destination + path[len(source) :]: artifact
                for path, artifact in self._artifacts.items()
                if path.startswith(prefix)
            }
            self._artifacts = {
                path: artifact
                for path, artifact in self._artifacts.items()
                if not path.startswith(prefix)
            } | moved

    @property
    def artifacts(self) -> dict[str, RecordedArtifact]:
        """Return the recorded artifacts by absolute path."""

        with self._lock:
            return dict(self._artifacts)
