"""Compact fact-cache codecs for discovered files whose raw contents are re-read live."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.discovery.models import (
    DiscoveredSourceFile,
    DiscoveredSqlTestFile,
)


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
