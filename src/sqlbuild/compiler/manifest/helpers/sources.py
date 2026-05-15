"""Source node serialization for dbt-compatible manifest."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledSource
from sqlbuild.compiler.manifest.constants import RESOURCE_TYPE_SOURCE
from sqlbuild.compiler.manifest.helpers.shared import build_source_columns_dict
from sqlbuild.spec.models.source import SourceEntry


def build_source_node(
    *,
    source: CompiledSource,
    project_name: str,
) -> dict[str, object]:
    """Build one dbt-compatible source node dict."""

    entry: SourceEntry = source.source_entry
    unique_id: str = f"source.{project_name}.{entry.name}"
    identifier: str = entry.table if entry.table is not None else entry.name

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
        "meta": dict(entry.meta) if entry.meta else {},
        "source_meta": {},
        "tags": [],
        "config": {},
        "patch_path": None,
        "unrendered_config": {},
        "relation_name": None,
        "created_at": 0.0,
    }
