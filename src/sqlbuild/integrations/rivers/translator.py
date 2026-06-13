"""SQLBuild-to-Rivers translation hooks."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


class SqlBuildRiversTranslator:
    """Default mapping from SQLBuild DAG records to Rivers metadata."""

    def get_asset_name(self, node: Mapping[str, Any]) -> str:
        return "__".join(str(part) for part in node["asset_key"])

    def get_group_name(self, node: Mapping[str, Any]) -> str | None:
        group_name: str = str(node.get("group") or node.get("project_name") or "sqlbuild")
        return group_name.replace("-", "_")

    def get_tags(self, node: Mapping[str, Any]) -> list[str]:
        tags: list[str] = [f"sqlbuild/kind:{node.get('kind', '')}"]
        for tag in node.get("tags", ()):
            tag_value: str = _normalize_tag(str(tag))
            if tag_value:
                tags.append(tag_value)
        return tags

    def get_kinds(self, node: Mapping[str, Any]) -> list[str]:
        kind: str = str(node.get("kind"))
        if kind == "model":
            materialization_type: str = str(node.get("materialization_type") or "table")
            if materialization_type == "view":
                return ["sqlbuild", "view"]
            return ["sqlbuild", "table"]
        if kind in {"source", "loader", "seed", "udf", "table_fn", "task", "asset"}:
            return ["sqlbuild", kind]
        return ["sqlbuild"]

    def get_metadata(self, node: Mapping[str, Any]) -> dict[str, str]:
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
        return {key: _metadata_value(value) for key, value in metadata.items() if value is not None}


def _metadata_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _normalize_tag(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-/]+", "_", value).strip("_")
