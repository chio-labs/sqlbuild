"""Checksummed, atomically replaced storage for one reusable compile result."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import uuid
import zlib
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO, cast

from sqlbuild.cli.compile_reuse.constants import (
    REUSE_ENTRY_BYTE_ORDER,
    REUSE_ENTRY_CHECKSUM_BYTES,
    REUSE_ENTRY_LENGTH_BYTES,
    REUSE_ENTRY_MAGIC,
    REUSE_ENTRY_SUFFIX,
    REUSE_FORMAT_VERSION,
    REUSE_MAX_ENTRY_BYTES,
    REUSE_MAX_STORED_ENTRIES,
    REUSE_STDOUT_SEPARATOR,
    REUSE_STDOUT_SUFFIX,
)
from sqlbuild.cli.compile_reuse.exceptions import CompileReuseEntryError
from sqlbuild.cli.compile_reuse.models import (
    SettingsEnvironmentInputs,
    StoredCompileHeader,
    StoredCompileInputs,
    StoredCompileOutput,
    StoredProjectFile,
)
from sqlbuild.cli.compile_reuse.types import FileStamp

_TIMINGS_SPAN_LENGTH: int = 2
_STAMP_FIELD_COUNT: int = 6
_PROJECT_FILE_FIELD_COUNT: int = 8
_SEARCH_PATH_FIELD_COUNT: int = 2
_MODULE_FIELD_COUNT: int = 3


def read_entry_header(*, path: Path) -> StoredCompileHeader | None:
    """Read and verify the stored inputs, treating every fault as a cache miss."""

    try:
        with open(path, "rb") as handle:
            if handle.read(len(REUSE_ENTRY_MAGIC)) != REUSE_ENTRY_MAGIC:
                return None
            metadata: bytes = _read_section(handle=handle)
            if handle.read(1):
                return None
        payload: object = json.loads(metadata)
        return _header(payload=payload)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError):
        return None


def read_entry_stdout(*, path: Path, header: StoredCompileHeader) -> str | None:
    """Read and verify the stored stdout once every input matched."""

    stdout_path: Path = path.parent / header.output.stdout_file
    try:
        stdout: bytes = stdout_path.read_bytes()
        if (
            len(stdout) > REUSE_MAX_ENTRY_BYTES
            or zlib.crc32(stdout) != header.output.stdout_checksum
        ):
            return None
        text: str = stdout.decode("utf-8", "surrogateescape")
    except (OSError, UnicodeError, ValueError):
        return None
    return text if len(text) == header.output.stdout_length else None


def write_entry(
    *,
    path: Path,
    inputs: StoredCompileInputs,
    output: StoredCompileOutput,
    stdout: str,
) -> None:
    """Publish one entry and its stdout atomically, filling in the stdout file and checksum."""

    encoded_stdout: bytes = stdout.encode("utf-8", "surrogateescape")
    stdout_file: str = f"{path.stem}{REUSE_STDOUT_SEPARATOR}{uuid.uuid4().hex}{REUSE_STDOUT_SUFFIX}"
    stored_output: StoredCompileOutput = replace(
        output, stdout_file=stdout_file, stdout_checksum=zlib.crc32(encoded_stdout)
    )
    metadata: bytes = _metadata(inputs=inputs, output=stored_output)
    if len(metadata) + len(encoded_stdout) > REUSE_MAX_ENTRY_BYTES:
        remove_entry(path=path)
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _publish_file(path=path.parent / stdout_file, contents=encoded_stdout)
        _publish_file(path=path, contents=_framed_metadata(metadata=metadata))
        _remove_side_files(entry_path=path, keep=stdout_file)
        _prune_entries(directory=path.parent, keep=path)
    except OSError:
        remove_entry(path=path)


def rewrite_entry_inputs(
    *, path: Path, header: StoredCompileHeader, inputs: StoredCompileInputs
) -> None:
    """Replace only the stored inputs of an entry, keeping its stored stdout file."""

    metadata: bytes = _metadata(inputs=inputs, output=header.output)
    with contextlib.suppress(OSError):
        _publish_file(path=path, contents=_framed_metadata(metadata=metadata))


def remove_entry(*, path: Path) -> None:
    """Remove one stored entry and its stored stdout when they exist."""

    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)
    _remove_side_files(entry_path=path, keep=None)


def _publish_file(*, path: Path, contents: bytes) -> None:
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            _ = handle.write(contents)
        os.replace(temporary_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary_path)
        raise


def _metadata(*, inputs: StoredCompileInputs, output: StoredCompileOutput) -> bytes:
    return json.dumps(_payload(inputs=inputs, output=output), separators=(",", ":")).encode(
        "utf-8", "surrogateescape"
    )


def _framed_metadata(*, metadata: bytes) -> bytes:
    return b"".join(
        (
            REUSE_ENTRY_MAGIC,
            len(metadata).to_bytes(REUSE_ENTRY_LENGTH_BYTES, REUSE_ENTRY_BYTE_ORDER),
            zlib.crc32(metadata).to_bytes(REUSE_ENTRY_CHECKSUM_BYTES, REUSE_ENTRY_BYTE_ORDER),
            metadata,
        )
    )


def _remove_side_files(*, entry_path: Path, keep: str | None) -> None:
    """Remove every file stored beside an entry except keep, including older releases' files."""

    prefix: str = f"{entry_path.stem}{REUSE_STDOUT_SEPARATOR}"
    try:
        candidates: list[Path] = list(entry_path.parent.iterdir())
    except OSError:
        return
    for candidate in candidates:
        if candidate.name.startswith(prefix) and candidate.name != keep:
            with contextlib.suppress(OSError):
                candidate.unlink()


def _read_section(*, handle: BinaryIO) -> bytes:
    length: int = int.from_bytes(handle.read(REUSE_ENTRY_LENGTH_BYTES), REUSE_ENTRY_BYTE_ORDER)
    checksum: int = int.from_bytes(handle.read(REUSE_ENTRY_CHECKSUM_BYTES), REUSE_ENTRY_BYTE_ORDER)
    if length > REUSE_MAX_ENTRY_BYTES:
        raise CompileReuseEntryError("stored compile section is too large")
    data: bytes = handle.read(length)
    if len(data) != length or zlib.crc32(data) != checksum:
        raise CompileReuseEntryError("stored compile section is truncated or corrupt")
    return data


def _prune_entries(*, directory: Path, keep: Path) -> None:
    entries: list[tuple[int, Path]] = []
    for candidate in directory.iterdir():
        if candidate.suffix != REUSE_ENTRY_SUFFIX or candidate == keep:
            continue
        with contextlib.suppress(OSError):
            entries.append((candidate.stat().st_mtime_ns, candidate))
    entries.sort(reverse=True)
    for _, stale in entries[REUSE_MAX_STORED_ENTRIES - 1 :]:
        remove_entry(path=stale)


def _payload(*, inputs: StoredCompileInputs, output: StoredCompileOutput) -> dict[str, object]:
    return {
        "format": REUSE_FORMAT_VERSION,
        "invocation_digest": inputs.invocation_digest,
        "runtime": inputs.runtime,
        "environment_names": list(inputs.environment_names),
        "environment_digest": inputs.environment_digest,
        "search_path": [list(item) for item in inputs.search_path],
        "modules": [list(item) for item in inputs.modules],
        "project_files": {
            path: [*item.stamp, item.digest, item.racy]
            for path, item in inputs.project_files.items()
        },
        "target_files": {path: list(stamp) for path, stamp in inputs.target_files.items()},
        "stderr_lines": list(output.stderr_lines),
        "exit_code": output.exit_code,
        "timings_span": None if output.timings_span is None else list(output.timings_span),
        "stdout_length": output.stdout_length,
        "stdout_checksum": output.stdout_checksum,
        "stdout_file": output.stdout_file,
        "target_tree": inputs.target_tree,
        "settings_inputs": [
            {
                "case_sensitive": item.case_sensitive,
                "names": list(item.names),
                "prefixes": list(item.prefixes),
                "env_files": list(item.env_files),
                "secrets_dirs": list(item.secrets_dirs),
            }
            for item in inputs.settings_inputs
        ],
        "settings_digest": inputs.settings_digest,
    }


def _header(*, payload: object) -> StoredCompileHeader:
    fields: dict[str, object] = _mapping(payload)
    if fields.get("format") != REUSE_FORMAT_VERSION:
        raise CompileReuseEntryError("unknown stored compile format")
    runtime: dict[str, object] = _mapping(fields["runtime"])
    span: tuple[int, int] | None = _timings_span(fields["timings_span"])
    return StoredCompileHeader(
        inputs=StoredCompileInputs(
            invocation_digest=_string(fields["invocation_digest"]),
            runtime={_string(key): _string(value) for key, value in runtime.items()},
            environment_names=tuple(_string(name) for name in _list(fields["environment_names"])),
            environment_digest=_string(fields["environment_digest"]),
            search_path=tuple(
                (_string(item[0]), _integer(item[1]))
                for item in _rows(value=fields["search_path"], width=_SEARCH_PATH_FIELD_COUNT)
            ),
            modules=tuple(
                (_string(item[0]), _integer(item[1]), _integer(item[2]))
                for item in _rows(value=fields["modules"], width=_MODULE_FIELD_COUNT)
            ),
            project_files={
                _string(path): _project_file(item)
                for path, item in _mapping(fields["project_files"]).items()
            },
            target_files={
                _string(path): _stamp(item)
                for path, item in _mapping(fields["target_files"]).items()
            },
            target_tree=_boolean(fields["target_tree"]),
            settings_inputs=tuple(
                _settings_inputs(item) for item in _list(fields["settings_inputs"])
            ),
            settings_digest=_string(fields["settings_digest"]),
        ),
        output=StoredCompileOutput(
            stderr_lines=tuple(_string(line) for line in _list(fields["stderr_lines"])),
            exit_code=_integer(fields["exit_code"]),
            timings_span=span,
            stdout_length=_integer(fields["stdout_length"]),
            stdout_checksum=_integer(fields["stdout_checksum"]),
            stdout_file=_stdout_file(fields["stdout_file"]),
        ),
    )


def _settings_inputs(value: object) -> SettingsEnvironmentInputs:
    fields: dict[str, object] = _mapping(value)
    return SettingsEnvironmentInputs(
        case_sensitive=_boolean(fields["case_sensitive"]),
        names=_strings(fields["names"]),
        prefixes=_strings(fields["prefixes"]),
        env_files=_strings(fields["env_files"]),
        secrets_dirs=_strings(fields["secrets_dirs"]),
    )


def _stdout_file(value: object) -> str:
    name: str = _string(value)
    if os.path.basename(name) != name or not name.endswith(REUSE_STDOUT_SUFFIX):
        raise CompileReuseEntryError("invalid stored stdout file name")
    return name


def _timings_span(value: object) -> tuple[int, int] | None:
    if value is None:
        return None
    row: list[object] = _rows(value=[value], width=_TIMINGS_SPAN_LENGTH)[0]
    return _integer(row[0]), _integer(row[1])


def _project_file(value: object) -> StoredProjectFile:
    if type(value) is not list or len(value) != _PROJECT_FILE_FIELD_COUNT:
        raise CompileReuseEntryError("invalid stored project file")
    row: list[object] = cast(list[object], value)
    digest: object = row[6]
    racy: object = row[7]
    if type(racy) is not bool or not (digest is None or type(digest) is str):
        raise CompileReuseEntryError("invalid stored project file")
    return StoredProjectFile(stamp=_stamp(row[:_STAMP_FIELD_COUNT]), digest=digest, racy=racy)


def _stamp(value: object) -> FileStamp:
    if type(value) is not list or len(value) != _STAMP_FIELD_COUNT:
        raise CompileReuseEntryError("invalid stored file stamp")
    kind, size, mtime_ns, ctime_ns, inode, link = cast(list[object], value)
    if (
        type(kind) is not str
        or type(size) is not int
        or type(mtime_ns) is not int
        or type(ctime_ns) is not int
        or type(inode) is not int
        or not (link is None or type(link) is str)
    ):
        raise CompileReuseEntryError("invalid stored file stamp")
    return FileStamp(kind, size, mtime_ns, ctime_ns, inode, link)


def _rows(*, value: object, width: int) -> list[list[object]]:
    rows: list[list[object]] = [_list(row) for row in _list(value)]
    if any(len(row) != width for row in rows):
        raise CompileReuseEntryError("invalid stored row")
    return rows


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise CompileReuseEntryError("invalid stored list")
    return cast(list[object], value)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CompileReuseEntryError("invalid stored mapping")
    return cast(dict[str, object], value)


def _strings(value: object) -> tuple[str, ...]:
    return tuple(_string(item) for item in _list(value))


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise CompileReuseEntryError("invalid stored boolean")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise CompileReuseEntryError("invalid stored string")
    return value


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CompileReuseEntryError("invalid stored integer")
    return value
