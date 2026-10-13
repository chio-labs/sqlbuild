"""Helpers for lineage cache fingerprint tests."""

from __future__ import annotations

import glob
import hashlib
import inspect
import json
import os
from collections.abc import Callable, Iterator
from importlib.metadata import version
from pathlib import Path
from types import TracebackType
from typing import Protocol

import pytest

_CACHE_ALGORITHM_VERSION: str = "relation-lineage-graph-v4"


def fingerprint_prefix(*, cli_vars: dict[str, object]) -> bytes:
    """The cache key prefix: algorithm, installed version and canonical `cli_vars` JSON."""

    return (
        _CACHE_ALGORITHM_VERSION.encode("ascii")
        + version("sqlbuild").encode("utf-8")
        + json.dumps(
            cli_vars,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    )


class _ScandirListing(Protocol):
    """The part of `os.scandir`'s iterator the interrupted listing wraps."""

    def close(self) -> None: ...


class _InterruptedListing:
    """A `scandir` iterator whose first step fails after the directory opened."""

    def __init__(self, listing: _ScandirListing) -> None:
        self._listing: _ScandirListing = listing

    def __enter__(self) -> _InterruptedListing:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._listing.close()

    def __iter__(self) -> Iterator[os.DirEntry[str]]:
        return self

    def __next__(self) -> os.DirEntry[str]:
        raise OSError(5, "Input/output error")

    def close(self) -> None:
        self._listing.close()


class _NoStringGlobber:
    """Stands in for `glob._StringGlobber` on Pythons whose `rglob` does not use it."""


def interrupt_listing(*, monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    """Make every `scandir` of `directory` fail mid-listing, wherever glob binds `scandir`."""

    real_scandir: Callable[..., _ScandirListing] = os.scandir
    target: str = os.path.abspath(directory)

    def scandir(path: str | os.PathLike[str] = ".") -> object:
        listing: _ScandirListing = real_scandir(path)
        choices: dict[bool, object] = {True: _InterruptedListing(listing), False: listing}
        return choices[os.path.abspath(os.fspath(path)) == target]

    globber: object = getattr(glob, "_StringGlobber", _NoStringGlobber)
    bound_early: bool = getattr(globber, "scandir", None) is real_scandir
    replacements: dict[bool, object] = {
        True: staticmethod(scandir),
        False: inspect.getattr_static(globber, "scandir", None),
    }
    monkeypatch.setattr(os, "scandir", scandir)
    monkeypatch.setattr(globber, "scandir", replacements[bound_early], raising=False)


def expected_fingerprint(
    *,
    project_dir: Path,
    prefix: bytes,
    hashed_files: tuple[str, ...],
    environment_names: tuple[str, ...],
) -> str:
    """The cache key over exactly `hashed_files`, in this platform's path order."""

    digest: hashlib._Hash = hashlib.sha256(prefix)
    for path in sorted(project_dir / relative_path for relative_path in hashed_files):
        relative_path: str = path.relative_to(project_dir).as_posix()
        contents: bytes = path.read_bytes()
        digest.update(len(relative_path).to_bytes(8, byteorder="big"))
        digest.update(relative_path.encode("utf-8"))
        digest.update(len(contents).to_bytes(8, byteorder="big"))
        digest.update(contents)
    for name in sorted(environment_names):
        digest.update(name.encode("ascii"))
        digest.update(os.environ.get(name, "<missing>").encode("utf-8"))
    return digest.hexdigest()
