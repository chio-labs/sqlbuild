"""SQL model files discovered by the native engine, materialised as Python discovery records."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    materialise_native_files,
    native_collection,
    native_locations,
    native_payload_error,
    native_project_tree,
    native_request,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery._helpers.sql.declarations import (
    parse_model_constant_declarations,
    parse_model_enum_declarations,
)
from sqlbuild.compiler.discovery._helpers.sql.model_files import project_native_header_values
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.constants import (
    REMOVED_SQL_MODEL_HEADER_KEYS,
    SQL_MODEL_HEADER_KEYS,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile, DiscoveryFileFault
from sqlbuild.compiler.discovery.types import NativeFiles, NativeLocation
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage


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
        files: NativeFiles = native_collection(
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
            ),
            project_dir=project_dir,
        )
        seed_snapshot_listings(project_dir=project_dir, tree=tree)
    report_native_answer(stage=NativeStage.DISCOVERY, kind="model_file_listings")
    return materialise_native_files(
        project_dir=project_dir,
        files=(
            (Path(relative_path), payload)
            for relative_path, payload in files
            if selected_model_names is None or Path(relative_path).stem in selected_model_names
        ),
        build=lambda relative_path, payload: _model_file(
            project_dir=project_dir,
            relative_path=relative_path,
            payload=payload,
            extract_implicit_alias_columns=extract_implicit_alias_columns,
        ),
        on_fault=on_fault,
    )


def _model_file(
    *,
    project_dir: Path,
    relative_path: Path,
    payload: tuple[object, ...],
    extract_implicit_alias_columns: bool,
) -> DiscoveredSqlModelFile:
    file_path: Path = project_dir / relative_path
    error: Exception | None = native_payload_error(payload=payload, file_path=file_path)
    if error is not None:
        raise error
    _tag, contents, values, header_locations, output_locations, query_sql = payload
    header_values: dict[str, object] = project_native_header_values(cast(dict[str, object], values))
    return DiscoveredSqlModelFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=str(contents),
        header_values=header_values,
        header_column_locations=native_locations(
            locations=cast(list[NativeLocation], header_locations), relative_path=relative_path
        ),
        output_column_locations=native_locations(
            locations=cast(list[NativeLocation], output_locations), relative_path=relative_path
        ),
        query_sql=str(query_sql),
        enum_declarations=parse_model_enum_declarations(
            raw_value=header_values.get("enums"),
            model_name=file_path.stem,
            relative_path=relative_path,
        ),
        constant_declarations=parse_model_constant_declarations(
            raw_value=header_values.get("constants"),
            model_name=file_path.stem,
            relative_path=relative_path,
        ),
        extract_implicit_alias_columns=extract_implicit_alias_columns,
    )
