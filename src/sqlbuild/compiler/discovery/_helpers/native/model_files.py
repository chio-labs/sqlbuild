"""SQL model files discovered by the native engine as native records."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    materialise_native_files,
    native_collection,
    native_payload_error,
    native_project_tree,
    native_request,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.constants import (
    REMOVED_SQL_MODEL_HEADER_KEYS,
    SQL_MODEL_HEADER_KEYS,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile, DiscoveryFileFault
from sqlbuild.compiler.discovery.types import NativeModelFiles

_RAISED_TAG: str = "raised"


def discover_native_model_files(
    *,
    project_dir: Path,
    extract_implicit_alias_columns: bool,
    extract_output_column_locations: bool,
    selected_model_names: frozenset[str] | None = None,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
) -> tuple[DiscoveredSqlModelFile, ...]:
    """Discover the (selected) model files natively, reporting failing files to `on_fault`."""

    with DirectorySnapshot.scope(project_dir=project_dir):
        tree: _native.NativeProjectTree = native_project_tree(project_dir)
        files: NativeModelFiles = native_collection(
            result=_native.discover_model_files(
                native_request(
                    project_dir=project_dir,
                    fields={
                        "supported_keys": sorted(SQL_MODEL_HEADER_KEYS),
                        "removed_keys": sorted(REMOVED_SQL_MODEL_HEADER_KEYS),
                        "extract_implicit_alias_columns": extract_implicit_alias_columns,
                        "extract_output_column_locations": extract_output_column_locations,
                    },
                ),
                tree,
                project_dir,
            ),
            project_dir=project_dir,
        )
        seed_snapshot_listings(project_dir=project_dir, tree=tree)
    return materialise_native_files(
        project_dir=project_dir,
        files=(
            (relative_path, item)
            for relative_path, item in files
            if selected_model_names is None or relative_path.stem in selected_model_names
        ),
        build=lambda relative_path, item: _model_file(
            project_dir=project_dir, relative_path=relative_path, item=item
        ),
        on_fault=on_fault,
    )


def _model_file(*, project_dir: Path, relative_path: Path, item: object) -> DiscoveredSqlModelFile:
    if isinstance(item, DiscoveredSqlModelFile):
        return item
    payload: tuple[object, ...] = cast(tuple[object, ...], item)
    if payload[0] == _RAISED_TAG:
        raise cast(Exception, payload[1])
    error: Exception | None = native_payload_error(
        payload=payload, file_path=project_dir / relative_path
    )
    raise error if error is not None else ValueError(payload)
