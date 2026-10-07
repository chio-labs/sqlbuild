"""SQL unit-test and scenario files discovered by the native engine, as Python records."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    materialise_native_files,
    native_collection,
    native_failure,
    native_payload_error,
    native_project_tree,
    native_request,
    native_text_runtime,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery._helpers.sql.model_files import project_native_header_values
from sqlbuild.compiler.discovery._helpers.sql.scenarios import build_sql_scenario_file
from sqlbuild.compiler.discovery._helpers.sql.tests import (
    build_sql_test_block,
    validate_sql_test_names,
)
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.constants import (
    SQL_SCENARIO_HEADER_KEYS,
    SQL_TEST_HEADER_KEYS,
    SQL_TESTS_OWNERSHIP_ROOT,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
    DiscoveryFileFault,
)
from sqlbuild.compiler.discovery.types import NativeFiles

type _NativeDiscovery = Callable[[dict[str, object], _native.NativeProjectTree], object]


def discover_native_test_files(
    *,
    project_dir: Path,
    selected_paths: frozenset[Path] | None = None,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
) -> tuple[DiscoveredSqlTestFile, ...]:
    """Discover the (selected) SQL test files natively, reporting failing files to `on_fault`."""

    files: NativeFiles = _native_files(
        project_dir=project_dir, discover=_native.discover_sql_test_files
    )
    return materialise_native_files(
        project_dir=project_dir,
        files=(
            (Path(relative_path), payload)
            for relative_path, payload in files
            if selected_paths is None or (project_dir / relative_path).resolve() in selected_paths
        ),
        build=lambda relative_path, payload: _test_file(
            project_dir=project_dir, relative_path=relative_path, payload=payload
        ),
        on_fault=on_fault,
    )


def discover_native_scenario_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSqlScenarioFile, ...]:
    """Discover scenario files natively, reporting failing files to `on_fault`."""

    files: NativeFiles = _native_files(
        project_dir=project_dir, discover=_native.discover_scenario_files
    )
    return materialise_native_files(
        project_dir=project_dir,
        files=((Path(relative_path), payload) for relative_path, payload in files),
        build=lambda relative_path, payload: _scenario_file(
            project_dir=project_dir, relative_path=relative_path, payload=payload
        ),
        on_fault=on_fault,
    )


def parse_native_sql_test_contents(
    *, contents: str, file_path: Path
) -> tuple[DiscoveredSqlTestBlock, ...]:
    """Parse in-memory SQL test contents into ordered blocks, as test discovery does."""

    payload: tuple[object, ...] = _native.parse_sql_test_contents(
        _text_request(file_path), contents
    )
    error: Exception | None = native_payload_error(payload=payload, file_path=file_path)
    if error is not None:
        raise error
    _tag, _contents, native_blocks, block_failure = payload
    return _test_blocks(
        file_path=file_path,
        native_blocks=cast(list[tuple[dict[str, object], str]], native_blocks),
        block_failure=cast(tuple[object, ...] | None, block_failure),
    )


def _text_request(file_path: Path) -> dict[str, object]:
    return {
        "file_path": str(file_path),
        "test_keys": sorted(SQL_TEST_HEADER_KEYS),
        "scenario_keys": sorted(SQL_SCENARIO_HEADER_KEYS),
        **native_text_runtime(),
    }


def _native_files(*, project_dir: Path, discover: _NativeDiscovery) -> NativeFiles:
    with DirectorySnapshot.scope(project_dir=project_dir):
        tree: _native.NativeProjectTree = native_project_tree(project_dir)
        files: NativeFiles = native_collection(
            result=cast(
                NativeFiles | tuple[object, ...],
                discover(
                    native_request(
                        project_dir=project_dir,
                        fields={
                            "test_keys": sorted(SQL_TEST_HEADER_KEYS),
                            "scenario_keys": sorted(SQL_SCENARIO_HEADER_KEYS),
                        },
                    ),
                    tree,
                ),
            ),
            project_dir=project_dir,
        )
        seed_snapshot_listings(project_dir=project_dir, tree=tree)
    return files


def _test_file(
    *, project_dir: Path, relative_path: Path, payload: tuple[object, ...]
) -> DiscoveredSqlTestFile:
    file_path: Path = project_dir / relative_path
    error: Exception | None = native_payload_error(payload=payload, file_path=file_path)
    if error is not None:
        raise error
    _tag, native_contents, native_blocks, block_failure = payload
    return DiscoveredSqlTestFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=str(native_contents),
        blocks=_test_blocks(
            file_path=file_path,
            native_blocks=cast(list[tuple[dict[str, object], str]], native_blocks),
            block_failure=cast(tuple[object, ...] | None, block_failure),
        ),
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
    return _scenario_file_from_payload(
        payload=payload, file_path=project_dir / relative_path, relative_path=relative_path
    )


def _scenario_file_from_payload(
    *, payload: tuple[object, ...], file_path: Path, relative_path: Path
) -> DiscoveredSqlScenarioFile:
    error: Exception | None = native_payload_error(payload=payload, file_path=file_path)
    if error is not None:
        raise error
    _tag, contents, values, sql_body = payload
    return build_sql_scenario_file(
        header_values=project_native_header_values(cast(dict[str, object], values)),
        sql_body=str(sql_body),
        contents=str(contents),
        file_path=file_path,
        relative_path=relative_path,
    )
