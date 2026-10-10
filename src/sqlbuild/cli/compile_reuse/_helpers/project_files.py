"""Stat walk, content digests, and change detection for project input files."""

from __future__ import annotations

import hashlib
import os
import stat

import sqlbuild._native as _native
from sqlbuild.cli.compile_reuse.constants import (
    BROKEN_LINK_KIND,
    DIGEST_SIZE_BYTES,
    DIRECTORY_KIND,
    DIRECTORY_LINK_KIND,
    EXCLUDED_DIRECTORIES,
    EXCLUDED_ROOT_DIRECTORIES,
    FILE_KIND,
    FILE_LINK_KIND,
    NATIVE_DIGEST_PREFIX,
    OUTPUT_FILE_DESCRIPTORS,
    PRESENCE_ONLY_FILE_SUFFIXES,
    PRESENCE_ONLY_KIND,
    RACY_WINDOW_NS,
    READ_CHUNK_BYTES,
    SPECIAL_FILE_KIND,
)
from sqlbuild.cli.compile_reuse.models import ProjectFilesComparison, StoredProjectFile
from sqlbuild.cli.compile_reuse.types import FileStamp
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.main.report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite, NativeStage

_DIRECTORY_STAMP: FileStamp = FileStamp(DIRECTORY_KIND, 0, 0, 0, 0, None)
_PRESENCE_STAMP: FileStamp = FileStamp(PRESENCE_ONLY_KIND, 0, 0, 0, 0, None)
_PRESENCE_ONLY_KINDS: frozenset[str] = frozenset(
    {DIRECTORY_KIND, DIRECTORY_LINK_KIND, BROKEN_LINK_KIND, PRESENCE_ONLY_KIND}
)
_HASHABLE_KINDS: frozenset[str] = frozenset({FILE_KIND, FILE_LINK_KIND})


def snapshot_project_files(*, project_dir: str) -> dict[str, FileStamp]:
    """Stat every compile-relevant path under the project, keyed by relative path."""

    output_files: frozenset[tuple[int, int]] = _redirected_output_files()
    native: dict[str, FileStamp] | None = _native_snapshot(
        project_dir=project_dir, output_files=output_files
    )
    if native is not None:
        return native
    stamps: dict[str, FileStamp] = {}
    prefix_length: int = len(project_dir) + 1
    visited_links: set[str] = {os.path.realpath(project_dir)}
    pending: list[tuple[str, bool]] = [(project_dir, True)]
    while pending:
        directory, is_root = pending.pop()
        for entry in _directory_entries(directory=directory):
            relative_path: str = entry.path[prefix_length:]
            stamp: FileStamp | None = _entry_stamp(
                entry=entry, is_root=is_root, output_files=output_files
            )
            if stamp is None:
                continue
            stamps[relative_path] = stamp
            if stamp.kind == DIRECTORY_KIND:
                pending.append((entry.path, False))
            elif stamp.kind == DIRECTORY_LINK_KIND:
                resolved: str = os.path.realpath(entry.path)
                if resolved not in visited_links:
                    visited_links.add(resolved)
                    pending.append((entry.path, False))
    return stamps


def _native_snapshot(
    *, project_dir: str, output_files: frozenset[tuple[int, int]]
) -> dict[str, FileStamp] | None:
    if not native_stage_enabled(NativeStage.COMPILE_OUTPUTS):
        return None
    rows: list[tuple[str, str, int, int, int, int, str | None]] | None = (
        _native.snapshot_project_paths(
            project_dir,
            {
                "excluded": sorted(EXCLUDED_DIRECTORIES),
                "excluded_root": sorted(EXCLUDED_ROOT_DIRECTORIES),
                "presence_suffixes": list(PRESENCE_ONLY_FILE_SUFFIXES),
                "output_files": sorted(output_files),
            },
        )
    )
    if rows is None:
        report_native_fallback(site=NativeFallbackSite.COMPILE_REUSE_SNAPSHOT)
        return None
    report_native_answer(stage=NativeStage.COMPILE_OUTPUTS, kind="snapshot_paths", units=len(rows))
    return {
        relative_path: FileStamp(kind, size, mtime_ns, ctime_ns, inode, link)
        for relative_path, kind, size, mtime_ns, ctime_ns, inode, link in rows
    }


def project_file_digests(*, project_dir: str, relative_paths: list[str]) -> list[str | None]:
    """Content digests of project input files; native digests carry their own prefix."""

    paths: list[str] = [os.path.join(project_dir, path) for path in relative_paths]
    if not native_stage_enabled(NativeStage.COMPILE_OUTPUTS):
        return [file_digest(path=path) for path in paths]
    digests: list[str | None] = _native.digest_files(paths)
    report_native_answer(
        stage=NativeStage.COMPILE_OUTPUTS,
        kind="project_file_digests",
        units=sum(digest is not None for digest in digests),
    )
    return [None if digest is None else NATIVE_DIGEST_PREFIX + digest for digest in digests]


def file_digest(*, path: str) -> str | None:
    """Return the content digest of one file, or None when it cannot be read."""

    digest: hashlib.blake2b = hashlib.blake2b(digest_size=DIGEST_SIZE_BYTES)
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(READ_CHUNK_BYTES):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def compare_project_files(
    *,
    project_dir: str,
    stored: dict[str, StoredProjectFile],
    current: dict[str, FileStamp],
) -> ProjectFilesComparison:
    """Compare stat identities, hashing content only where stat changed or may be racy."""

    verified: dict[str, str] = {}
    changed: ProjectFilesComparison = ProjectFilesComparison(unchanged=False, verified=verified)
    if len(stored) != len(current):
        return changed
    for relative_path, stamp in current.items():
        previous: StoredProjectFile | None = stored.get(relative_path)
        if previous is None or not _same_identity(stamp=stamp, recorded=previous.stamp):
            return changed
        if stamp.kind in _PRESENCE_ONLY_KINDS or (stamp == previous.stamp and not previous.racy):
            continue
        if stamp.kind not in _HASHABLE_KINDS or previous.digest is None:
            return changed
        digest: str | None = project_file_digests(
            project_dir=project_dir, relative_paths=[relative_path]
        )[0]
        if digest is None or digest != previous.digest:
            return changed
        verified[relative_path] = digest
    return ProjectFilesComparison(unchanged=True, verified=verified)


def carried_forward_digests(
    *,
    stored: dict[str, StoredProjectFile],
    current: dict[str, FileStamp],
    verified: dict[str, str],
) -> dict[str, str]:
    """Return digests still valid for current files, without reading any content."""

    digests: dict[str, str] = dict(verified)
    for relative_path, stamp in current.items():
        previous: StoredProjectFile | None = stored.get(relative_path)
        if (
            relative_path not in digests
            and previous is not None
            and previous.digest is not None
            and not previous.racy
            and previous.stamp == stamp
        ):
            digests[relative_path] = previous.digest
    return digests


def restamped_paths(
    *, stored: dict[str, StoredProjectFile], current: dict[str, FileStamp]
) -> frozenset[str]:
    """Return hashable files whose stat identity moved since the stored compile."""

    return frozenset(
        relative_path
        for relative_path, stamp in current.items()
        if stamp.kind in _HASHABLE_KINDS
        and (previous := stored.get(relative_path)) is not None
        and previous.stamp.kind == stamp.kind
        and previous.stamp != stamp
    )


def stored_project_files(
    *, snapshot: dict[str, FileStamp], digests: dict[str, str], snapshot_ns: int
) -> dict[str, StoredProjectFile]:
    """Pair each project path's stat identity with any digest already known for it."""

    return {
        relative_path: StoredProjectFile(
            stamp=stamp,
            digest=digests.get(relative_path),
            racy=is_racy(stamp=stamp, snapshot_ns=snapshot_ns),
        )
        for relative_path, stamp in snapshot.items()
    }


def needs_refresh(*, stored: dict[str, StoredProjectFile], current: dict[str, FileStamp]) -> bool:
    """Return whether a hit verified any file by content, so its new stamp is worth storing."""

    return any(
        (previous := stored.get(relative_path)) is not None
        and (previous.racy or previous.stamp != stamp)
        and stamp.kind in _HASHABLE_KINDS
        for relative_path, stamp in current.items()
    )


def is_racy(*, stamp: FileStamp, snapshot_ns: int) -> bool:
    """Return whether a same-tick edit after the snapshot could leave this stamp unchanged."""

    return (
        stamp.kind in _HASHABLE_KINDS
        and max(stamp.mtime_ns, stamp.ctime_ns) >= snapshot_ns - RACY_WINDOW_NS
    )


def with_missing_digests(
    *,
    project_dir: str,
    snapshot: dict[str, FileStamp],
    digests: dict[str, str],
    paths: frozenset[str],
    snapshot_ns: int,
) -> dict[str, str]:
    """Return digests extended with racy files, plus the given paths, that still lack one."""

    completed: dict[str, str] = dict(digests)
    missing: list[str] = [
        relative_path
        for relative_path, stamp in snapshot.items()
        if stamp.kind in _HASHABLE_KINDS
        and relative_path not in completed
        and (relative_path in paths or is_racy(stamp=stamp, snapshot_ns=snapshot_ns))
    ]
    for relative_path, digest in zip(
        missing,
        project_file_digests(project_dir=project_dir, relative_paths=missing) if missing else [],
        strict=True,
    ):
        if digest is not None:
            completed[relative_path] = digest
    return completed


def pending_digest_bytes(
    *, snapshot: dict[str, FileStamp], digests: dict[str, str], paths: frozenset[str]
) -> int:
    """Return how many bytes hashing the given paths that still lack a digest would read."""

    return sum(
        snapshot[relative_path].size
        for relative_path in paths
        if relative_path in snapshot and relative_path not in digests
    )


def _same_identity(*, stamp: FileStamp, recorded: FileStamp) -> bool:
    return (
        stamp.kind == recorded.kind
        and stamp.link == recorded.link
        and (stamp.kind in _PRESENCE_ONLY_KINDS or stamp.size == recorded.size)
    )


def _directory_entries(*, directory: str) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(directory) as entries:
            return list(entries)
    except OSError:
        return []


def _entry_stamp(
    *, entry: os.DirEntry[str], is_root: bool, output_files: frozenset[tuple[int, int]]
) -> FileStamp | None:
    if entry.is_symlink():
        return _link_stamp(entry=entry, is_root=is_root)
    if entry.is_dir(follow_symlinks=False):
        return None if _excluded_directory(name=entry.name, is_root=is_root) else _DIRECTORY_STAMP
    if entry.name.endswith(PRESENCE_ONLY_FILE_SUFFIXES):
        return _PRESENCE_STAMP
    try:
        status: os.stat_result = entry.stat(follow_symlinks=False)
    except OSError:
        return None
    if (status.st_dev, status.st_ino) in output_files:
        return _PRESENCE_STAMP
    return _file_stamp(status=status, link=None)


def _link_stamp(*, entry: os.DirEntry[str], is_root: bool) -> FileStamp | None:
    try:
        link: str = os.readlink(entry.path)
    except OSError:
        return None
    try:
        status: os.stat_result = os.stat(entry.path)
    except OSError:
        return FileStamp(BROKEN_LINK_KIND, 0, 0, 0, 0, link)
    if not stat.S_ISDIR(status.st_mode):
        return _file_stamp(status=status, link=link)
    if _excluded_directory(name=entry.name, is_root=is_root):
        return None
    return FileStamp(DIRECTORY_LINK_KIND, 0, 0, 0, 0, link)


def _redirected_output_files() -> frozenset[tuple[int, int]]:
    """Identify stdout and stderr files, which hold this command's output, not its inputs."""

    identities: set[tuple[int, int]] = set()
    for descriptor in OUTPUT_FILE_DESCRIPTORS:
        try:
            status: os.stat_result = os.fstat(descriptor)
        except OSError:
            continue
        if stat.S_ISREG(status.st_mode):
            identities.add((status.st_dev, status.st_ino))
    return frozenset(identities)


def _excluded_directory(*, name: str, is_root: bool) -> bool:
    return name in EXCLUDED_DIRECTORIES or (is_root and name in EXCLUDED_ROOT_DIRECTORIES)


def _file_stamp(*, status: os.stat_result, link: str | None) -> FileStamp:
    kind: str = SPECIAL_FILE_KIND
    if stat.S_ISREG(status.st_mode):
        kind = FILE_KIND if link is None else FILE_LINK_KIND
    return FileStamp(
        kind, status.st_size, status.st_mtime_ns, status.st_ctime_ns, status.st_ino, link
    )
