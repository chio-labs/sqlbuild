"""Source and schema YAML files read and loaded by the native engine."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.filesystem.scoped_paths import project_relative_path
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    materialise_native_files,
    native_collection,
    native_display_prefix,
    native_payload_error,
    native_project_tree,
    native_unreadable_path_payload,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery._helpers.yml.file_paths import (
    schema_file_paths,
    source_file_paths,
)
from sqlbuild.compiler.discovery._helpers.yml.schema import parse_loaded_schema_yml
from sqlbuild.compiler.discovery._helpers.yml.sources import parse_loaded_sources_yml
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.constants import (
    NATIVE_SCHEMA_YAML_KIND,
    NATIVE_SOURCE_YAML_KIND,
    NATIVE_YAML_BATCH_BYTES,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSourceFile,
    DiscoveryFileFault,
)

type _Payload = tuple[object, ...]


def discover_native_source_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSourceFile, ...]:
    """Discover source YAML files natively, reporting failing files to `on_fault`."""

    with DirectorySnapshot.scope(project_dir=project_dir):
        file_paths: tuple[Path, ...] = source_file_paths(project_dir=project_dir)
        return materialise_native_files(
            project_dir=project_dir,
            files=(
                (project_relative_path(path=file_path, project_dir=project_dir), payload)
                for file_path, payload in _native_payloads(
                    project_dir=project_dir, file_paths=file_paths, kind=NATIVE_SOURCE_YAML_KIND
                )
            ),
            build=lambda relative_path, payload: _source_file(
                project_dir=project_dir, relative_path=relative_path, payload=payload
            ),
            on_fault=on_fault,
        )


def discover_native_schema_files(*, project_dir: Path) -> tuple[DiscoveredSchemaFile, ...]:
    """Discover model schema.yml and seed declaration files natively."""

    with DirectorySnapshot.scope(project_dir=project_dir):
        file_paths: tuple[Path, ...] = schema_file_paths(project_dir=project_dir)
        return tuple(
            _schema_file(project_dir=project_dir, file_path=file_path, payload=payload)
            for file_path, payload in _native_payloads(
                project_dir=project_dir, file_paths=file_paths, kind=NATIVE_SCHEMA_YAML_KIND
            )
        )


def _source_file(
    *, project_dir: Path, relative_path: Path, payload: _Payload
) -> DiscoveredSourceFile:
    file_path: Path = project_dir / relative_path
    contents, loaded = _loaded(payload=payload, file_path=file_path)
    return DiscoveredSourceFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=contents,
        source_entries=parse_loaded_sources_yml(loaded=loaded, file_path=file_path),
    )


def _schema_file(*, project_dir: Path, file_path: Path, payload: _Payload) -> DiscoveredSchemaFile:
    contents, loaded = _loaded(payload=payload, file_path=file_path)
    model_entries, seed_entries = parse_loaded_schema_yml(loaded=loaded, file_path=file_path)
    return DiscoveredSchemaFile(
        file_path=file_path,
        relative_path=project_relative_path(path=file_path, project_dir=project_dir),
        contents=contents,
        model_entries=model_entries,
        seed_entries=seed_entries,
    )


def _loaded(*, payload: _Payload, file_path: Path) -> tuple[str, object]:
    error: Exception | None = native_payload_error(payload=payload, file_path=file_path)
    if error is not None:
        raise error
    _tag, contents, loaded = payload
    return str(contents), loaded


def _relative_text(*, project_dir: Path, file_path: Path) -> str:
    return project_relative_path(path=file_path, project_dir=project_dir).as_posix()


def _native_payloads(
    *, project_dir: Path, file_paths: tuple[Path, ...], kind: str
) -> Iterator[tuple[Path, _Payload]]:
    """Load the files natively in batches bounded by size, releasing each file once used."""

    if not file_paths:
        return
    tree: _native.NativeProjectTree = native_project_tree(project_dir)
    request: dict[str, object] = {
        "project_dir": str(project_dir),
        "display_prefix": native_display_prefix(project_dir),
        "kind": kind,
    }
    for batch in _batches(file_paths=file_paths):
        relative_texts: list[str] = [
            _relative_text(project_dir=project_dir, file_path=path) for path in batch
        ]
        unnamed: list[_Payload] = [
            native_unreadable_path_payload(project_dir=project_dir, relative_text=text)
            for text in relative_texts
        ]
        payloads: list[_Payload] = native_collection(
            result=_native.load_yaml_files(
                request,
                [
                    text
                    for text, failure in zip(relative_texts, unnamed, strict=True)
                    if not failure
                ],
                tree,
            ),
            project_dir=project_dir,
        )
        seed_snapshot_listings(project_dir=project_dir, tree=tree)
        payloads.reverse()
        for file_path, failure in zip(batch, unnamed, strict=True):
            yield file_path, failure or payloads.pop()


def _batches(*, file_paths: tuple[Path, ...]) -> Iterator[tuple[Path, ...]]:
    batch: list[Path] = []
    batch_bytes: int = 0
    for file_path in file_paths:
        size: int = _file_size(file_path)
        if batch and batch_bytes + size > NATIVE_YAML_BATCH_BYTES:
            yield tuple(batch)
            batch, batch_bytes = [], 0
        batch.append(file_path)
        batch_bytes += size
    if batch:
        yield tuple(batch)


def _file_size(file_path: Path) -> int:
    try:
        return file_path.stat().st_size
    except OSError:
        return 0
