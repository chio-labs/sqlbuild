"""Shared serialization helpers for manifest node building."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.spec.models.schema import SchemaColumn, SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceColumnEntry

_RESOURCE_TYPE_PREFIX: dict[str, str] = {
    CompiledResourceType.MODEL: "model",
    CompiledResourceType.SOURCE: "source",
    CompiledResourceType.SEED: "seed",
    CompiledResourceType.DBT_REF: "model",
    CompiledResourceType.AUDIT: "test",
    CompiledResourceType.SQL_TEST: "test",
}


def build_fqn(*, project_name: str, relative_path: Path) -> list[str]:
    """Build a dbt-style fully qualified name list from project name and path."""

    parts: list[str] = [project_name]
    parent: Path = relative_path.parent
    part: str
    for part in parent.parts:
        parts.append(part)
    stem: str = relative_path.stem
    parts.append(stem)
    return parts


def build_columns_dict(
    schema_entry: SchemaModelEntry | SchemaSeedEntry | None,
) -> dict[str, dict[str, object]]:
    """Build a dbt-compatible columns dict from schema entry columns."""

    if schema_entry is None:
        return {}
    result: dict[str, dict[str, object]] = {}
    column: SchemaColumn
    for column in schema_entry.columns:
        result[column.name] = {
            "name": column.name,
            "description": column.description or "",
            "meta": dict(column.meta) if column.meta else {},
            "data_type": column.type,
            "constraints": [],
            "quote": None,
            "tags": [],
        }
    return result


def build_source_columns_dict(
    columns: tuple[SourceColumnEntry, ...],
) -> dict[str, dict[str, object]]:
    """Build a dbt-compatible columns dict from source column entries."""

    result: dict[str, dict[str, object]] = {}
    column: SourceColumnEntry
    for column in columns:
        result[column.name] = {
            "name": column.name,
            "description": column.description or "",
            "meta": dict(column.meta) if column.meta else {},
            "data_type": column.type,
            "constraints": [],
            "quote": None,
            "tags": [],
        }
    return result


def build_config_dict(values: dict[str, object]) -> dict[str, object]:
    """Build a dbt-compatible config dict from model config values."""

    materialized: object = values.get("materialized", "view")
    result: dict[str, object] = {
        "enabled": values.get("enabled", True),
        "alias": values.get("alias"),
        "schema": values.get("schema"),
        "database": values.get("database"),
        "tags": _config_tags(values),
        "meta": {},
        "group": None,
        "materialized": str(materialized) if materialized is not None else "view",
        "incremental_strategy": values.get("incremental_strategy"),
        "persist_docs": {},
        "post-hook": [],
        "pre-hook": [],
        "quoting": {},
        "column_types": {},
        "full_refresh": None,
        "unique_key": values.get("unique_key"),
        "on_schema_change": values.get("on_schema_change", "ignore"),
        "on_configuration_change": "apply",
        "grants": {},
        "packages": [],
        "docs": {"show": True, "node_color": None},
        "contract": {"enforced": False, "alias_types": True},
    }
    return result


def build_depends_on(
    *,
    deps: tuple[CompiledObjectKey, ...],
    project_name: str,
) -> dict[str, list[str]]:
    """Build a dbt-compatible depends_on dict from compiled deps."""

    node_ids: list[str] = []
    dep: CompiledObjectKey
    for dep in deps:
        dep_id: str = _key_to_unique_id(dep, project_name)
        node_ids.append(dep_id)
    return {
        "macros": [],
        "nodes": node_ids,
    }


def _key_to_unique_id(key: CompiledObjectKey, project_name: str) -> str:
    """Convert a CompiledObjectKey to a dbt-style unique_id."""

    resource_prefix: str = _RESOURCE_TYPE_PREFIX.get(str(key.resource_type), "model")
    return f"{resource_prefix}.{project_name}.{key.name}"


def _config_tags(values: dict[str, object]) -> list[str]:
    """Extract tags from config values as a list."""

    raw: object | None = values.get("tags")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, tuple):
        return [str(item) for item in raw]
    return []
