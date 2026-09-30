"""Filesystem discovery for SQL-native unit test files."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.cached_files import (
    decode_cached_sql_test_file,
    encode_cached_sql_test_file,
)
from sqlbuild.compiler.discovery._helpers.sql.tests import (
    parse_sql_test_file,
    prepare_sql_test_file_headers,
)
from sqlbuild.compiler.discovery.constants import (
    DISCOVERY_SQL_TEST_FACT_KIND,
    SQL_TESTS_OWNERSHIP_ROOT,
)
from sqlbuild.compiler.discovery.exceptions import SqlTestParseError
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
    DiscoveryFileFault,
)
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore

_TEST_FILE_BATCH_SIZE: int = 512


def discover_sql_test_files(
    *,
    project_dir: Path,
    file_paths: tuple[Path, ...],
    on_fault: Callable[[DiscoveryFileFault], None] | None,
    fact_cache: FactCacheStore | None = None,
) -> tuple[DiscoveredSqlTestFile, ...]:
    """Read and parse ordered SQL test paths through bounded native header batches."""

    loaded: list[tuple[Path, str | None, Exception | None]] = []
    for file_path in file_paths:
        try:
            loaded.append((file_path, file_path.read_text(encoding="utf-8"), None))
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            loaded.append((file_path, None, error))

    cache_keys: dict[Path, str] = (
        {
            file_path: fact_cache.key(
                DISCOVERY_SQL_TEST_FACT_KIND, str(project_dir), str(file_path), contents
            )
            for file_path, contents, error in loaded
            if contents is not None and error is None
        }
        if fact_cache is not None and fact_cache.enabled
        else {}
    )
    cached_facts: dict[str, object] = (
        fact_cache.read_many(
            tuple((_fact_slot(file_path), cache_key) for file_path, cache_key in cache_keys.items())
        )
        if fact_cache is not None
        else {}
    )
    discovered: list[DiscoveredSqlTestFile] = []
    for batch_start in range(0, len(loaded), _TEST_FILE_BATCH_SIZE):
        batch: list[tuple[Path, str | None, Exception | None]] = loaded[
            batch_start : batch_start + _TEST_FILE_BATCH_SIZE
        ]
        _prepare_batch([item for item in batch if cache_keys.get(item[0]) not in cached_facts])
        for file_path, contents, read_error in batch:
            if read_error is not None:
                if on_fault is None:
                    raise read_error
                on_fault(_file_fault(project_dir=project_dir, path=file_path, error=read_error))
                continue
            if contents is None:
                raise SqlTestParseError("SQL test file read returned neither contents nor an error")
            cache_key: str | None = cache_keys.get(file_path)
            cached_test_file: DiscoveredSqlTestFile | None = (
                decode_cached_sql_test_file(
                    fact=cached_facts.get(cache_key), file_path=file_path, contents=contents
                )
                if cache_key is not None
                else None
            )
            if cached_test_file is not None:
                discovered.append(cached_test_file)
                continue
            try:
                blocks: tuple[DiscoveredSqlTestBlock, ...] = parse_sql_test_file(
                    contents=contents, file_path=file_path
                )
            except (OSError, UnicodeError, ValueError, SyntaxError) as error:
                if on_fault is None:
                    raise
                on_fault(_file_fault(project_dir=project_dir, path=file_path, error=error))
                continue
            test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=contents,
                blocks=blocks,
                ownership_root=Path(SQL_TESTS_OWNERSHIP_ROOT),
            )
            discovered.append(test_file)
            if fact_cache is not None and cache_key is not None:
                fact_cache.stage(
                    key=cache_key,
                    slot=_fact_slot(file_path),
                    value=encode_cached_sql_test_file(test_file),
                )
    return tuple(discovered)


def _fact_slot(file_path: Path) -> str:
    return f"{DISCOVERY_SQL_TEST_FACT_KIND}:{file_path}"


def _prepare_batch(batch: list[tuple[Path, str | None, Exception | None]]) -> None:
    contents_batch: list[str] = []
    for _path, contents, error in batch:
        if contents is not None and error is None:
            contents_batch.append(contents)
    try:
        prepare_sql_test_file_headers(contents_batch)
    except (OSError, UnicodeError, ValueError, SyntaxError):
        pass


def _file_fault(*, project_dir: Path, path: Path, error: Exception) -> DiscoveryFileFault:
    try:
        relative_path: Path | None = path.relative_to(project_dir)
    except ValueError:
        relative_path = None
    return DiscoveryFileFault(
        path=relative_path,
        message=str(error).replace(str(project_dir), "."),
    )
