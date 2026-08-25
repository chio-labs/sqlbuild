"""Model node serialization for dbt-compatible manifest."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.discovery.models import PythonHookEntry, SqlHookEntry
from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.manifest._helpers.shared import (
    build_columns_dict,
    build_config_dict,
    build_depends_on,
    build_fqn,
)
from sqlbuild.compiler.manifest.constants import CHECKSUM_HASH_NAME, RESOURCE_TYPE_MODEL
from sqlbuild.compiler.planner.models import ModelPlanEntry


def build_model_node(
    *,
    model: CompiledModel,
    plan_entry: ModelPlanEntry | None,
    project_name: str,
    python_hook_metadata: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build one dbt-compatible model node dict."""

    unique_id: str = f"model.{project_name}.{model.name}"
    relative_path: Path = model.relative_path
    raw_code: str = model.query_sql
    compiled_code: str = plan_entry.resolved_sql if plan_entry is not None else raw_code
    query_hash: str = compute_query_hash(raw_code)

    return {
        "database": model.destination.database,
        "schema": model.destination.schema,
        "name": model.name,
        "resource_type": RESOURCE_TYPE_MODEL,
        "package_name": project_name,
        "path": str(relative_path),
        "original_file_path": str(relative_path),
        "unique_id": unique_id,
        "fqn": build_fqn(project_name=project_name, relative_path=relative_path),
        "alias": model.destination.name,
        "checksum": {
            "name": CHECKSUM_HASH_NAME,
            "checksum": query_hash,
        },
        "config": build_config_dict(model.config.values),
        "tags": _extract_tags(model),
        "description": _extract_description(model),
        "columns": build_columns_dict(model.schema_entry),
        "meta": _extract_meta(
            model=model,
            python_hook_metadata=python_hook_metadata or {},
        ),
        "group": None,
        "docs": {"show": True, "node_color": None},
        "patch_path": None,
        "build_path": None,
        "unrendered_config": {},
        "created_at": 0.0,
        "config_call_dict": {},
        "unrendered_config_call_dict": {},
        "relation_name": model.destination.qualified_name,
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


def _extract_meta(
    *, model: CompiledModel, python_hook_metadata: dict[str, dict[str, object]]
) -> dict[str, object]:
    """Extract meta from schema entry."""

    meta: dict[str, object] = {}
    if model.schema_entry is not None and model.schema_entry.meta is not None:
        meta.update(model.schema_entry.meta)
    lifecycle_hooks: dict[str, list[dict[str, object]]] = {}
    hook_key: str
    for hook_key in ("pre_hooks", "post_hooks"):
        serialized: list[dict[str, object]] = _serialize_hooks(
            value=model.config.values.get(hook_key),
            python_hook_metadata=python_hook_metadata,
        )
        if serialized:
            lifecycle_hooks[hook_key] = serialized
    if lifecycle_hooks:
        meta["sqlbuild"] = {"lifecycle_hooks": lifecycle_hooks}
    return meta


def _serialize_hooks(
    *, value: object, python_hook_metadata: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    if not isinstance(value, list | tuple):
        return []
    hooks: list[dict[str, object]] = []
    entry: object
    for entry in value:
        if isinstance(entry, SqlHookEntry):
            hook: dict[str, object] = {
                "type": "sql",
                "statement": entry.statement,
            }
            if entry.name is not None:
                hook["name"] = entry.name
            if entry.relative_path is not None:
                hook["relative_path"] = entry.relative_path.as_posix()
            hooks.append(hook)
        elif isinstance(entry, PythonHookEntry):
            python_hook: dict[str, object] = {
                "type": "python",
                "name": entry.name,
                "kwargs": entry.kwargs,
            }
            python_hook.update(python_hook_metadata.get(entry.name, {}))
            hooks.append(python_hook)
    return hooks
