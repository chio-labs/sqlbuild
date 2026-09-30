"""Compact fact-cache codecs for discovered files whose raw contents are re-read live."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.yml.sources import parse_sources_yml
from sqlbuild.compiler.discovery.constants import DISCOVERY_SOURCE_FACT_KIND
from sqlbuild.compiler.discovery.models import (
    DiscoveredSourceFile,
    DiscoveredSqlTestFile,
)
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore


def parse_source_file_with_cache(
    *,
    project_dir: Path,
    file_path: Path,
    relative_path: Path,
    fact_cache: FactCacheStore | None,
) -> DiscoveredSourceFile:
    """Parse one source YAML file, reusing its exact cached fact when the contents match."""

    contents: str = file_path.read_text(encoding="utf-8")
    cache_key: str | None = (
        fact_cache.key(DISCOVERY_SOURCE_FACT_KIND, str(project_dir), str(file_path), contents)
        if fact_cache is not None and fact_cache.enabled
        else None
    )
    slot: str = f"{DISCOVERY_SOURCE_FACT_KIND}:{file_path}"
    if fact_cache is not None and cache_key is not None:
        cached: DiscoveredSourceFile | None = decode_cached_source_file(
            fact=fact_cache.read_many(((slot, cache_key),)).get(cache_key),
            file_path=file_path,
            contents=contents,
        )
        if cached is not None:
            return cached
    source_file: DiscoveredSourceFile = DiscoveredSourceFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=contents,
        source_entries=parse_sources_yml(contents=contents, file_path=file_path),
    )
    if fact_cache is not None and cache_key is not None:
        fact_cache.stage(key=cache_key, slot=slot, value=encode_cached_source_file(source_file))
    return source_file


def encode_cached_source_file(source_file: DiscoveredSourceFile) -> object:
    """Return a source fact without raw YAML."""

    return replace(source_file, contents="")


def decode_cached_source_file(
    *, fact: object, file_path: Path, contents: str
) -> DiscoveredSourceFile | None:
    """Rebuild one cached source file from its fact and exact live YAML."""

    if not isinstance(fact, DiscoveredSourceFile) or fact.file_path != file_path:
        return None
    return replace(fact, contents=contents)


def encode_cached_sql_test_file(test_file: DiscoveredSqlTestFile) -> object:
    """Return a SQL test fact without raw file contents."""

    return replace(test_file, contents="")


def decode_cached_sql_test_file(
    *, fact: object, file_path: Path, contents: str
) -> DiscoveredSqlTestFile | None:
    """Rebuild one cached SQL test file from its fact and exact live contents."""

    if not isinstance(fact, DiscoveredSqlTestFile) or fact.file_path != file_path:
        return None
    return replace(fact, contents=contents)
