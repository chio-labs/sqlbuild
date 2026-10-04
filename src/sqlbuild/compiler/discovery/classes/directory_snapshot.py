"""One shared directory snapshot for a discovery pass."""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from sqlbuild.compiler.discovery.types import DirectorySnapshotEntry

_CASE_PROBE: str = "A"
_DIRECTORIES_QUERY: str = ""


class DirectorySnapshot:
    """Directory listings read once per discovery pass and shared by every glob in it."""

    active: ClassVar[ContextVar[DirectorySnapshot | None]] = ContextVar(
        "sqlbuild_directory_snapshot", default=None
    )

    def __init__(self, *, project_dir: Path) -> None:
        self.project_dir: Path = project_dir
        self.memo: dict[object, object] = {}
        self._listings: dict[Path, tuple[DirectorySnapshotEntry, ...]] = {}
        self._matches: dict[tuple[Path, str], tuple[Path, ...]] = {}

    @classmethod
    @contextmanager
    def scope(cls, *, project_dir: Path) -> Iterator[DirectorySnapshot]:
        """Share one snapshot across every discovery query for the project inside the scope."""

        active: DirectorySnapshot | None = cls.active.get()
        if active is not None and active.project_dir == project_dir:
            yield active
            return
        tree: DirectorySnapshot = DirectorySnapshot(project_dir=project_dir)
        token: Token[DirectorySnapshot | None] = cls.active.set(tree)
        try:
            yield tree
        finally:
            cls.active.reset(token)

    @classmethod
    def current(cls, *, project_dir: Path) -> DirectorySnapshot:
        """Return the active snapshot for the project, or a single-use one outside a scope."""

        active: DirectorySnapshot | None = cls.active.get()
        if active is not None and active.project_dir == project_dir:
            return active
        return DirectorySnapshot(project_dir=project_dir)

    def rglob(self, *, root: Path, pattern: str) -> tuple[Path, ...]:
        """Return the paths ``root.rglob(pattern)`` yields for a single-name pattern, unordered."""

        match: Callable[[str], bool] = _name_matcher(pattern)
        return self._select(root=root, key=pattern, accept=lambda entry: match(entry.name))

    def directories(self, *, root: Path) -> tuple[Path, ...]:
        """Return every directory below ``root``, including unwalked directory links, unordered."""

        return self._select(root=root, key=_DIRECTORIES_QUERY, accept=lambda entry: entry.is_dir)

    def _select(
        self, *, root: Path, key: str, accept: Callable[[DirectorySnapshotEntry], bool]
    ) -> tuple[Path, ...]:
        cached: tuple[Path, ...] | None = self._matches.get((root, key))
        if cached is not None:
            return cached
        selected: list[Path] = []
        if root.is_dir():
            directory: Path
            for directory in self._walk(root=root):
                selected.extend(
                    directory / entry.name
                    for entry in self._listing(directory=directory)
                    if accept(entry)
                )
        result: tuple[Path, ...] = tuple(selected)
        self._matches[(root, key)] = result
        return result

    def _walk(self, *, root: Path) -> Iterator[Path]:
        pending: list[Path] = [root]
        while pending:
            directory: Path = pending.pop()
            yield directory
            pending.extend(
                directory / entry.name
                for entry in self._listing(directory=directory)
                if entry.is_walkable_dir
            )

    def _listing(self, *, directory: Path) -> tuple[DirectorySnapshotEntry, ...]:
        cached: tuple[DirectorySnapshotEntry, ...] | None = self._listings.get(directory)
        if cached is not None:
            return cached
        entries: list[DirectorySnapshotEntry] = []
        try:
            with os.scandir(directory) as scanned:
                entries.extend(
                    DirectorySnapshotEntry(
                        name=entry.name,
                        is_dir=_is_dir(entry=entry, follow_symlinks=True),
                        is_walkable_dir=_is_dir(entry=entry, follow_symlinks=False),
                    )
                    for entry in scanned
                )
        except OSError:
            entries = []
        listing: tuple[DirectorySnapshotEntry, ...] = tuple(entries)
        self._listings[directory] = listing
        return listing


def _is_dir(*, entry: os.DirEntry[str], follow_symlinks: bool) -> bool:
    try:
        return entry.is_dir(follow_symlinks=follow_symlinks)
    except OSError:
        return False


@lru_cache(maxsize=64)
def _name_matcher(pattern: str) -> Callable[[str], bool]:
    """Match names like ``Path.glob`` with the platform's default case sensitivity."""

    flags: int = 0 if os.path.normcase(_CASE_PROBE) == _CASE_PROBE else re.IGNORECASE
    compiled: re.Pattern[str] = re.compile(fnmatch.translate(pattern), flags)
    return lambda name: compiled.match(name) is not None
