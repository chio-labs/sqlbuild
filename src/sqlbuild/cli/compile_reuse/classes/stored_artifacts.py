"""Artifacts a stored compile left in target/, trusted while their stat identity is unchanged."""

from __future__ import annotations

from sqlbuild.cli.compile_reuse._helpers.target_files import path_stamp
from sqlbuild.cli.compile_reuse.types import FileStamp


class StoredArtifacts:
    """Answer whether an artifact still holds the bytes a stored compile recorded for it."""

    def __init__(self, *, stamps: dict[str, FileStamp], digests: dict[str, str]) -> None:
        self._stamps: dict[str, FileStamp] = stamps
        self._digests: dict[str, str] = digests

    def holds(self, *, path: str, digest: str | None) -> bool:
        """Return whether the file at path is unchanged since it was stored with this digest."""

        return (
            digest is not None
            and self._digests.get(path) == digest
            and self.unchanged_since_stored(path=path)
        )

    def unchanged_since_stored(self, *, path: str) -> bool:
        """Return whether the file at path still has the stat identity it was stored with."""

        stamp: FileStamp | None = self._stamps.get(path)
        return stamp is not None and path_stamp(path=path) == stamp
