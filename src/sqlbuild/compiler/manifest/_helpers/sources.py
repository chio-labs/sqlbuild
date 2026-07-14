"""Source node serialization for dbt-compatible manifest."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledSource
from sqlbuild.compiler.manifest._helpers.shared import build_source_columns_dict
from sqlbuild.compiler.manifest.constants import RESOURCE_TYPE_SOURCE
from sqlbuild.spec.contracts.models import SourceEntry


def build_source_node(
    *,
    source: CompiledSource,
    project_name: str,
    auto_load: bool = False,
) -> dict[str, object]:
    """Build one dbt-compatible source node dict."""

    entry: SourceEntry = source.source_entry
    unique_id: str = f"source.{project_name}.{entry.name}"
    identifier: str = entry.table if entry.table is not None else entry.name

    meta: dict[str, object] = dict(entry.meta) if entry.meta else {}
    if entry.loader is not None:
        sqlbuild_meta: dict[str, object] = {
            "loader": entry.loader,
            "auto_load": auto_load,
        }
        if entry.write_strategy is not None:
            sqlbuild_meta["write_strategy"] = entry.write_strategy.value
        if entry.cursor_column is not None:
            sqlbuild_meta["cursor_column"] = entry.cursor_column
        if entry.unique_key:
            sqlbuild_meta["unique_key"] = entry.unique_key
        meta["sqlbuild"] = sqlbuild_meta

    return {
        "database": entry.database,
        "schema": entry.schema or "",
        "name": entry.name,
        "resource_type": RESOURCE_TYPE_SOURCE,
        "package_name": project_name,
        "path": str(source.source_file.relative_path),
        "original_file_path": str(source.source_file.relative_path),
        "unique_id": unique_id,
        "fqn": [project_name, entry.name],
        "source_name": entry.name,
        "source_description": "",
        "loader": "",
        "identifier": identifier,
        "quoting": {},
        "loaded_at_field": None,
        "freshness": None,
        "external": None,
        "description": entry.description or "",
        "columns": build_source_columns_dict(entry.columns),
        "meta": meta,
        "source_meta": {},
        "tags": [],
        "config": {},
        "patch_path": None,
        "unrendered_config": {},
        "relation_name": None,
        "created_at": 0.0,
    }
