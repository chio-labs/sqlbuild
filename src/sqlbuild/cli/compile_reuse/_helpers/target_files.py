"""Stat identity of the artifacts a compile leaves in target/."""

from __future__ import annotations

import os

from sqlbuild.cli.compile_reuse._helpers.project_files import file_digest
from sqlbuild.cli.compile_reuse.constants import (
    COMPILED_DIRECTORY_NAME,
    FILE_KIND,
    RACY_WINDOW_NS,
    TARGET_DIRECTORY_NAME,
)
from sqlbuild.cli.compile_reuse.models import RecordedArtifact
from sqlbuild.cli.compile_reuse.types import FileStamp


def snapshot_target_files(
    *, project_dir: str, extra_paths: tuple[str, ...]
) -> dict[str, FileStamp]:
    """Stat every compiled artifact plus extra written artifacts, keyed by path."""

    stamps: dict[str, FileStamp] = {}
    pending: list[str] = [_compiled_root(project_dir=project_dir)]
    while pending:
        directory: str = pending.pop()
        try:
            entries: list[os.DirEntry[str]] = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                pending.append(entry.path)
                continue
            stamp: FileStamp | None = _path_stamp(path=entry.path)
            if stamp is not None:
                stamps[entry.path] = stamp
    for path in extra_paths:
        extra: FileStamp | None = _path_stamp(path=path)
        if extra is not None:
            stamps[path] = extra
    return stamps


def verified_target_files(
    *,
    project_dir: str,
    dag_path: str | None,
    artifacts: dict[str, RecordedArtifact],
    written: bool,
    since_ns: int,
) -> dict[str, FileStamp] | None:
    """Stamp this compile's artifacts, or return None when any changed since it wrote them."""

    compiled_prefix: str = _compiled_root(project_dir=project_dir) + os.sep
    expected: dict[str, RecordedArtifact] = {
        path: artifact
        for path, artifact in artifacts.items()
        if path.startswith(compiled_prefix) or path == dag_path
    }
    stamps: dict[str, FileStamp] = _target_stamps(
        project_dir=project_dir, paths=tuple(expected), tree=written
    )
    if stamps.keys() != expected.keys() or not all(
        _matches_recorded(path=path, stamp=stamp, artifact=expected[path], since_ns=since_ns)
        for path, stamp in stamps.items()
    ):
        return None
    if _target_stamps(project_dir=project_dir, paths=tuple(expected), tree=written) != stamps:
        return None
    return stamps


def target_files_unchanged(*, stored: dict[str, FileStamp], project_dir: str, tree: bool) -> bool:
    """Return whether every stored artifact is unchanged and, for a written tree, none was added."""

    return _target_stamps(project_dir=project_dir, paths=tuple(stored), tree=tree) == stored


def _target_stamps(*, project_dir: str, paths: tuple[str, ...], tree: bool) -> dict[str, FileStamp]:
    """Stamp the whole compiled tree plus extra paths, or only the given paths."""

    if not tree:
        return {path: stamp for path in paths if (stamp := _path_stamp(path=path)) is not None}
    compiled_prefix: str = _compiled_root(project_dir=project_dir) + os.sep
    extra_paths: tuple[str, ...] = tuple(
        path for path in paths if not path.startswith(compiled_prefix)
    )
    return snapshot_target_files(project_dir=project_dir, extra_paths=extra_paths)


def _matches_recorded(
    *, path: str, stamp: FileStamp, artifact: RecordedArtifact, since_ns: int
) -> bool:
    if artifact.digest is None:
        return stamp.size == artifact.size and stamp.mtime_ns == artifact.mtime_ns
    if max(stamp.mtime_ns, stamp.ctime_ns) < since_ns - RACY_WINDOW_NS:
        return True
    return file_digest(path=path) == artifact.digest


def _compiled_root(*, project_dir: str) -> str:
    return os.path.join(project_dir, TARGET_DIRECTORY_NAME, COMPILED_DIRECTORY_NAME)


def _path_stamp(*, path: str) -> FileStamp | None:
    try:
        status: os.stat_result = os.lstat(path)
    except OSError:
        return None
    return FileStamp(
        FILE_KIND, status.st_size, status.st_mtime_ns, status.st_ctime_ns, status.st_ino, None
    )
