"""Model node serialization for dbt-compatible manifest."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.manifest.constants import CHECKSUM_HASH_NAME, RESOURCE_TYPE_MODEL
from sqlbuild.compiler.manifest.helpers.shared import (
    build_columns_dict,
    build_config_dict,
    build_depends_on,
    build_fqn,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.shared.helpers.hashing import compute_query_hash


def build_model_node(
    *,
    model: CompiledModel,
    plan_entry: ModelPlanEntry | None,
    project_name: str,
) -> dict[str, object]:
    """Build one dbt-compatible model node dict."""

    unique_id: str = f"model.{project_name}.{model.name}"
    relative_path: Path = model.relative_path
    raw_code: str = model.query_sql
    compiled_code: str = plan_entry.resolved_sql if plan_entry is not None else raw_code
    query_hash: str = compute_query_hash(raw_code)

    return {
        "database": model.target.database,
        "schema": model.target.schema,
        "name": model.name,
        "resource_type": RESOURCE_TYPE_MODEL,
        "package_name": project_name,
        "path": str(relative_path),
        "original_file_path": str(relative_path),
        "unique_id": unique_id,
        "fqn": build_fqn(project_name=project_name, relative_path=relative_path),
        "alias": model.target.name,
        "checksum": {
            "name": CHECKSUM_HASH_NAME,
            "checksum": query_hash,
        },
        "config": build_config_dict(model.config.values),
        "tags": _extract_tags(model),
        "description": _extract_description(model),
        "columns": build_columns_dict(model.schema_entry),
        "meta": _extract_meta(model),
        "group": None,
        "docs": {"show": True, "node_color": None},
        "patch_path": None,
        "build_path": None,
        "unrendered_config": {},
        "created_at": 0.0,
        "config_call_dict": {},
        "unrendered_config_call_dict": {},
        "relation_name": model.target.qualified_name,
        "raw_code": raw_code,
        "compiled_code": compiled_code,
        "depends_on": build_depends_on(
            deps=model.deps,
            project_name=project_name,
        ),
    }


def _extract_tags(model: CompiledModel) -> list[str]:
    """Extract tags from model config."""

    raw: object | None = model.config.values.get("tags")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, tuple):
        return [str(item) for item in raw]
    return []


def _extract_description(model: CompiledModel) -> str:
    """Extract description from schema entry."""

    if model.schema_entry is not None and model.schema_entry.description is not None:
        return model.schema_entry.description
    return ""


def _extract_meta(model: CompiledModel) -> dict[str, object]:
    """Extract meta from schema entry."""

    if model.schema_entry is not None and model.schema_entry.meta is not None:
        return dict(model.schema_entry.meta)
    return {}
