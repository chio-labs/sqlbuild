"""SQL unit-test and scenario files discovered by the native engine, as Python records."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_scenario_files,
    discover_test_files,
)
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    native_discovery_supported,
    native_display_prefix,
    native_failure,
    native_project_tree,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery._helpers.sql.model_files import project_native_header_values
from sqlbuild.compiler.discovery._helpers.sql.scenarios import (
    build_sql_scenario_file,
    parse_sql_scenario_file,
)
from sqlbuild.compiler.discovery._helpers.sql.tests import (
    build_sql_test_block,
    parse_sql_test_file,
    validate_sql_test_names,
)
from sqlbuild.compiler.discovery.constants import (
    NATIVE_FAILED_TAG,
    NATIVE_UNREADABLE_TAG,
    SQL_SCENARIO_HEADER_KEYS,
    SQL_TEST_HEADER_KEYS,
    SQL_TESTS_OWNERSHIP_ROOT,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore

type _NativeFiles = list[tuple[str, tuple[object, ...]]]
type _NativeDiscovery = Callable[
    [dict[str, object], _native.NativeProjectTree], _NativeFiles | None
]


def discover_native_test_files(
    *, project_dir: Path, fact_cache: FactCacheStore | None = None
) -> tuple[DiscoveredSqlTestFile, ...]:
    """Discover SQL test files natively; Python, with its fact cache, runs where native cannot."""

    files: _NativeFiles | None = _native_files(
        project_dir=project_dir, discover=_native.discover_sql_test_files
    )
    if files is None:
        return discover_test_files(project_dir=project_dir, fact_cache=fact_cache)
    return tuple(
        _test_file(project_dir=project_dir, relative_path=Path(relative_path), payload=payload)
        for relative_path, payload in files
    )


def discover_native_scenario_files(*, project_dir: Path) -> tuple[DiscoveredSqlScenarioFile, ...]:
    """Discover scenario files natively; Python runs when native discovery cannot match it."""

    files: _NativeFiles | None = _native_files(
        project_dir=project_dir, discover=_native.discover_scenario_files
    )
    if files is None:
        return discover_scenario_files(project_dir=project_dir)
    return tuple(
        _scenario_file(project_dir=project_dir, relative_path=Path(relative_path), payload=payload)
        for relative_path, payload in files
    )


def _native_files(*, project_dir: Path, discover: _NativeDiscovery) -> _NativeFiles | None:
    display_prefix: str = native_display_prefix(project_dir)
    if not native_discovery_supported(project_dir=project_dir, display_prefix=display_prefix):
        return None
    tree: _native.NativeProjectTree = native_project_tree(project_dir)
    files: _NativeFiles | None = discover(
        {
            "project_dir": str(project_dir),
            "display_prefix": display_prefix,
            "test_keys": sorted(SQL_TEST_HEADER_KEYS),
            "scenario_keys": sorted(SQL_SCENARIO_HEADER_KEYS),
        },
        tree,
    )
    seed_snapshot_listings(project_dir=project_dir, tree=tree)
    return files


def _test_file(
    *, project_dir: Path, relative_path: Path, payload: tuple[object, ...]
) -> DiscoveredSqlTestFile:
    file_path: Path = project_dir / relative_path
    tag: object = payload[0]
    if tag == NATIVE_FAILED_TAG:
        raise native_failure(payload)
    contents: str
    blocks: tuple[DiscoveredSqlTestBlock, ...]
    if tag == NATIVE_UNREADABLE_TAG:
        contents = file_path.read_text(encoding="utf-8")
        blocks = parse_sql_test_file(contents=contents, file_path=file_path)
    else:
        _tag, native_contents, native_blocks, block_failure = payload
        contents = str(native_contents)
        blocks = _test_blocks(
            file_path=file_path,
            native_blocks=cast(list[tuple[dict[str, object], str]], native_blocks),
            block_failure=cast(tuple[object, ...] | None, block_failure),
        )
    return DiscoveredSqlTestFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=contents,
        blocks=blocks,
        ownership_root=Path(SQL_TESTS_OWNERSHIP_ROOT),
    )


def _test_blocks(
    *,
    file_path: Path,
    native_blocks: list[tuple[dict[str, object], str]],
    block_failure: tuple[object, ...] | None,
) -> tuple[DiscoveredSqlTestBlock, ...]:
    blocks: tuple[DiscoveredSqlTestBlock, ...] = tuple(
        build_sql_test_block(
            header_values=project_native_header_values(values),
            sql_body=sql_body,
            file_path=file_path,
            test_index=test_index,
        )
        for test_index, (values, sql_body) in enumerate(native_blocks, start=1)
    )
    if block_failure is not None:
        raise native_failure(block_failure)
    validate_sql_test_names(file_path=file_path, blocks=blocks)
    return blocks


def _scenario_file(
    *, project_dir: Path, relative_path: Path, payload: tuple[object, ...]
) -> DiscoveredSqlScenarioFile:
    file_path: Path = project_dir / relative_path
    tag: object = payload[0]
    if tag == NATIVE_FAILED_TAG:
        raise native_failure(payload)
    if tag == NATIVE_UNREADABLE_TAG:
        return parse_sql_scenario_file(
            contents=file_path.read_text(encoding="utf-8"),
            file_path=file_path,
            relative_path=relative_path,
        )
    _tag, contents, values, sql_body = payload
    return build_sql_scenario_file(
        header_values=project_native_header_values(cast(dict[str, object], values)),
        sql_body=str(sql_body),
        contents=str(contents),
        file_path=file_path,
        relative_path=relative_path,
    )
