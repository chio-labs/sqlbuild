"""SQLBuild-to-Dagster translation hooks."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from sqlbuild.integrations.dagster._helpers.imports import load_dagster
from sqlbuild.integrations.dagster.constants import SOURCE_NODE_KIND


class SqlBuildDagsterTranslator:
    """Default mapping from SQLBuild DAG records to Dagster metadata."""

    def get_asset_key(self, node: Mapping[str, Any]) -> Any:
        dg: Any = load_dagster()
        authored_asset_key: Sequence[object] | None = _authored_dagster_asset_key(node)
        if authored_asset_key is not None:
            return dg.AssetKey([str(part) for part in authored_asset_key])
        return dg.AssetKey([str(part) for part in node["asset_key"]])

    def is_asset_node(self, node: Mapping[str, Any]) -> bool:
        """Return whether SQLBuild owns this node as a Dagster asset."""

        return True

    def is_asset_check(self, check: Mapping[str, Any]) -> bool:
        """Return whether SQLBuild exposes this check through the multi-asset definition."""

        return True

    def get_group_name(self, node: Mapping[str, Any]) -> str | None:
        group_name: str = str(node.get("group") or node.get("project_name") or "sqlbuild")
        return group_name.replace("-", "_")

    def get_tags(self, node: Mapping[str, Any]) -> Mapping[str, str]:
        tags: dict[str, str] = {"sqlbuild/kind": str(node.get("kind", ""))}
        for tag in node.get("tags", ()):
            tag_key: str = _normalize_tag_key(str(tag))
            if tag_key:
                tags[tag_key] = ""
        return tags

    def get_metadata(self, node: Mapping[str, Any]) -> Mapping[str, Any]:
        metadata: dict[str, Any] = {
            "sqlbuild_id": node.get("id"),
            "sqlbuild_name": node.get("name"),
            "sqlbuild_kind": node.get("kind"),
            "sqlbuild_selector": node.get("name"),
        }
        for key in (
            "path",
            "target",
            "description",
            "sql",
            "columns",
            "column_lineage",
            "group",
            "language",
            "materialization_type",
            "return_kind",
            "loader",
            "meta",
        ):
            if key in node:
                metadata[key] = node[key]
        return metadata

    def get_description(self, node: Mapping[str, Any]) -> str | None:
        description: str = str(node.get("description") or _fallback_description(node))
        sql: object = node.get("sql")
        if isinstance(sql, str) and sql.strip():
            return f"{description}\n\n**SQLBuild SQL:**\n```sql\n{sql.strip()}\n```"
        path: object = node.get("path")
        if isinstance(path, str) and path:
            return f"{description}\n\n**Source file:** {_markdown_code_span(path)}"
        return description

    def get_check_name(self, check: Mapping[str, Any]) -> str:
        parts: list[str] = [str(check.get("kind", "check")), str(check.get("name", "check"))]
        if check.get("attached_column_name") is not None:
            parts.append(str(check["attached_column_name"]))
        elif check.get("attached_target_name") is not None:
            parts.append(str(check["attached_target_name"]))
        return "__".join(_normalize_name(part) for part in parts if part)

    def get_check_metadata(self, check: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "sqlbuild_check_id": check.get("id"),
            "sqlbuild_check_kind": check.get("kind"),
            "sqlbuild_check_name": check.get("name"),
            "sqlbuild_check_selector": check.get("id"),
        }


def _normalize_tag_key(value: str) -> str:
    normalized: str = re.sub(r"[^A-Za-z0-9_.\-/]+", "_", value).strip("_")
    return normalized


def _authored_dagster_asset_key(node: Mapping[str, Any]) -> Sequence[object] | None:
    if str(node.get("kind")) != SOURCE_NODE_KIND:
        return None
    meta: object = node.get("meta")
    if not isinstance(meta, Mapping):
        return None
    dagster_meta: object = meta.get("dagster")
    if not isinstance(dagster_meta, Mapping):
        return None
    asset_key: object = dagster_meta.get("asset_key")
    if not isinstance(asset_key, Sequence) or isinstance(asset_key, (str, bytes)) or not asset_key:
        return None
    return asset_key


def _normalize_name(value: str) -> str:
    normalized: str = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return normalized or "check"


def _markdown_code_span(value: str) -> str:
    longest_backtick_run: int = max(
        (len(match.group()) for match in re.finditer(r"`+", value)), default=0
    )
    delimiter: str = "`" * (longest_backtick_run + 1)
    padding: str = " " if value.startswith(("`", " ")) or value.endswith(("`", " ")) else ""
    return f"{delimiter}{padding}{value}{padding}{delimiter}"


def _fallback_description(node: Mapping[str, Any]) -> str:
    kind: str = str(node.get("kind") or "asset").replace("_", " ")
    name: str = str(node.get("name") or "unknown")
    target: object = node.get("target")
    qualified_name: str = ""
    if isinstance(target, Mapping):
        qualified_name = str(target.get("qualified_name") or "")
    relation_suffix: str = f" at `{qualified_name}`" if qualified_name else ""
    materialization: object = node.get("materialization_type")
    if materialization is not None:
        return f"SQLBuild {kind} `{name}` materialized as `{materialization}`{relation_suffix}."
    return f"SQLBuild {kind} `{name}`{relation_suffix}."
