"""Source and schema YAML files loaded by the native engine, with per-file Python loading."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.filesystem.cached_files import (
    parse_source_file_with_cache,
)
from sqlbuild.compiler.discovery._helpers.filesystem.core import discover_source_files
from sqlbuild.compiler.discovery._helpers.filesystem.scoped_paths import project_relative_path
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    materialise_native_files,
    native_discovery_supported,
    native_display_prefix,
    native_path_text_supported,
    native_project_tree,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery._helpers.yml.file_paths import (
    schema_file_paths,
    source_file_paths,
)
from sqlbuild.compiler.discovery._helpers.yml.schema import (
    parse_loaded_schema_yml,
    parse_schema_yml,
)
from sqlbuild.compiler.discovery._helpers.yml.sources import parse_loaded_sources_yml
from sqlbuild.compiler.discovery.constants import (
    NATIVE_LOADED_TAG,
    NATIVE_UNREADABLE_TAG,
    NATIVE_YAML_BATCH_BYTES,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSourceFile,
    DiscoveryFileFault,
)
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.spec.contracts.models import SchemaModelEntry, SchemaSeedEntry

type _Payload = tuple[object, ...]


def discover_native_source_files(
    *,
    project_dir: Path,
    fact_cache: FactCacheStore | None = None,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
) -> tuple[DiscoveredSourceFile, ...]:
    """Discover source YAML files natively, reporting failing files to `on_fault`."""

    file_paths: tuple[Path, ...] = source_file_paths(project_dir=project_dir)
    if not _native_supported(project_dir=project_dir, file_paths=file_paths):
        return discover_source_files(
            project_dir=project_dir, on_fault=on_fault, fact_cache=fact_cache
        )
    return materialise_native_files(
        project_dir=project_dir,
        files=(
            (project_relative_path(path=file_path, project_dir=project_dir), payload)
            for file_path, payload in _native_payloads(
                project_dir=project_dir, file_paths=file_paths
            )
        ),
        build=lambda relative_path, payload: _source_file(
            project_dir=project_dir,
            relative_path=relative_path,
            payload=payload,
            fact_cache=fact_cache,
        ),
        on_fault=on_fault,
    )


def _source_file(
    *,
    project_dir: Path,
    relative_path: Path,
    payload: _Payload,
    fact_cache: FactCacheStore | None,
) -> DiscoveredSourceFile:
    file_path: Path = project_dir / relative_path
    if payload[0] == NATIVE_LOADED_TAG:
        _tag, contents, loaded = payload
        return DiscoveredSourceFile(
            file_path=file_path,
            relative_path=relative_path,
            contents=str(contents),
            source_entries=parse_loaded_sources_yml(loaded=loaded, file_path=file_path),
        )
    return parse_source_file_with_cache(
        project_dir=project_dir,
        file_path=file_path,
        relative_path=relative_path,
        fact_cache=fact_cache,
    )


def discover_native_schema_files(*, project_dir: Path) -> tuple[DiscoveredSchemaFile, ...]:
    """Discover schema YAML files natively; Python loads any file native cannot reproduce."""

    file_paths: tuple[Path, ...] = schema_file_paths(project_dir=project_dir)
    payloads: Iterator[tuple[Path, _Payload]] = (
        _native_payloads(project_dir=project_dir, file_paths=file_paths)
        if _native_supported(project_dir=project_dir, file_paths=file_paths)
        else ((file_path, (NATIVE_UNREADABLE_TAG,)) for file_path in file_paths)
    )
    discovered: list[DiscoveredSchemaFile] = []
    for file_path, payload in payloads:
        contents: str
        entries: tuple[tuple[SchemaModelEntry, ...], tuple[SchemaSeedEntry, ...]]
        if payload[0] == NATIVE_LOADED_TAG:
            _tag, native_contents, loaded = payload
            contents = str(native_contents)
            entries = parse_loaded_schema_yml(loaded=loaded, file_path=file_path)
        else:
            contents = _python_contents(file_path=file_path, payload=payload)
            entries = parse_schema_yml(contents=contents, file_path=file_path)
        discovered.append(
            DiscoveredSchemaFile(
                file_path=file_path,
                relative_path=project_relative_path(path=file_path, project_dir=project_dir),
                contents=contents,
                model_entries=entries[0],
                seed_entries=entries[1],
            )
        )
    return tuple(discovered)


def _python_contents(*, file_path: Path, payload: _Payload) -> str:
    read: Callable[[], str] = {
        True: lambda: file_path.read_text(encoding="utf-8"),
        False: lambda: str(payload[1]),
    }[payload[0] == NATIVE_UNREADABLE_TAG]
    return read()


def _native_supported(*, project_dir: Path, file_paths: tuple[Path, ...]) -> bool:
    return (
        bool(file_paths)
        and native_discovery_supported(
            project_dir=project_dir, display_prefix=native_display_prefix(project_dir)
        )
        and all(
            native_path_text_supported(_relative_text(project_dir=project_dir, file_path=file_path))
            for file_path in file_paths
        )
    )


def _relative_text(*, project_dir: Path, file_path: Path) -> str:
    return project_relative_path(path=file_path, project_dir=project_dir).as_posix()


def _native_payloads(
    *, project_dir: Path, file_paths: tuple[Path, ...]
) -> Iterator[tuple[Path, _Payload]]:
    """Load the files natively in batches bounded by size, releasing each file once used."""

    tree: _native.NativeProjectTree = native_project_tree(project_dir)
    for batch in _batches(file_paths=file_paths):
        payloads: list[object] | None = _native.load_yaml_files(
            [_relative_text(project_dir=project_dir, file_path=path) for path in batch], tree
        )
        seed_snapshot_listings(project_dir=project_dir, tree=tree)
        pending: list[_Payload] = (
            [(NATIVE_UNREADABLE_TAG,)] * len(batch)
            if payloads is None
            else [cast(_Payload, payload) for payload in reversed(payloads)]
        )
        del payloads
        for file_path in batch:
            yield file_path, pending.pop()


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
