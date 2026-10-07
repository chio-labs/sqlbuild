"""SQL model files discovered by the native engine, materialised as Python discovery records."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.filesystem.core import discover_model_files
from sqlbuild.compiler.discovery._helpers.filesystem.model_files import (
    discover_matched_model_file,
)
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    native_discovery_supported,
    native_display_prefix,
    native_failure,
    native_locations,
    native_project_tree,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery._helpers.sql.declarations import (
    parse_model_constant_declarations,
    parse_model_enum_declarations,
)
from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    match_model_header,
    project_native_header_values,
)
from sqlbuild.compiler.discovery.constants import (
    NATIVE_FAILED_TAG,
    NATIVE_UNREADABLE_TAG,
    REMOVED_SQL_MODEL_HEADER_KEYS,
    SQL_MODEL_HEADER_KEYS,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.compiler.discovery.types import NativeLocation


def discover_native_model_files(
    *,
    project_dir: Path,
    extract_implicit_alias_columns: bool,
    extract_output_column_locations: bool,
) -> tuple[DiscoveredSqlModelFile, ...]:
    """Discover model files natively; Python runs when native discovery cannot match it."""

    display_prefix: str = native_display_prefix(project_dir)
    files: list[tuple[str, tuple[object, ...]]] | None = (
        _discover_native_files(
            project_dir=project_dir,
            display_prefix=display_prefix,
            extract_implicit_alias_columns=extract_implicit_alias_columns,
            extract_output_column_locations=extract_output_column_locations,
        )
        if native_discovery_supported(project_dir=project_dir, display_prefix=display_prefix)
        else None
    )
    if files is None:
        return discover_model_files(
            project_dir=project_dir,
            extract_implicit_alias_columns=extract_implicit_alias_columns,
            extract_output_column_locations=extract_output_column_locations,
        )
    return tuple(
        _model_file(
            project_dir=project_dir,
            relative_path=Path(relative_path),
            payload=payload,
            extract_implicit_alias_columns=extract_implicit_alias_columns,
            extract_output_column_locations=extract_output_column_locations,
        )
        for relative_path, payload in files
    )


def _discover_native_files(
    *,
    project_dir: Path,
    display_prefix: str,
    extract_implicit_alias_columns: bool,
    extract_output_column_locations: bool,
) -> list[tuple[str, tuple[object, ...]]] | None:
    tree: _native.NativeProjectTree = native_project_tree(project_dir)
    files: list[tuple[str, tuple[object, ...]]] | None = _native.discover_model_files(
        {
            "project_dir": str(project_dir),
            "display_prefix": display_prefix,
            "supported_keys": sorted(SQL_MODEL_HEADER_KEYS),
            "removed_keys": sorted(REMOVED_SQL_MODEL_HEADER_KEYS),
            "extract_implicit_alias_columns": extract_implicit_alias_columns,
            "extract_output_column_locations": extract_output_column_locations,
        },
        tree,
    )
    seed_snapshot_listings(project_dir=project_dir, tree=tree)
    return files


def _model_file(
    *,
    project_dir: Path,
    relative_path: Path,
    payload: tuple[object, ...],
    extract_implicit_alias_columns: bool,
    extract_output_column_locations: bool,
) -> DiscoveredSqlModelFile:
    file_path: Path = project_dir / relative_path
    tag: object = payload[0]
    if tag == NATIVE_UNREADABLE_TAG:
        contents: str = file_path.read_text(encoding="utf-8")
        return discover_matched_model_file(
            file_path=file_path,
            relative_path=relative_path,
            contents=contents,
            header_match=match_model_header(contents),
            extract_implicit_alias_columns=extract_implicit_alias_columns,
            extract_output_column_locations=extract_output_column_locations,
        )
    if tag == NATIVE_FAILED_TAG:
        raise native_failure(payload)
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
