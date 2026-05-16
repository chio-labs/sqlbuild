"""SQLBuild-to-Dagster translation hooks."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlbuild.integrations.dagster.helpers.imports import load_dagster


class SqlBuildDagsterTranslator:
    """Default mapping from SQLBuild DAG records to Dagster metadata."""

    def get_asset_key(self, node: Mapping[str, Any]) -> Any:
        dg: Any = load_dagster()
        return dg.AssetKey([str(part) for part in node["asset_key"]])

    def get_group_name(self, node: Mapping[str, Any]) -> str | None:
        group_name: str = str(node.get("project_name") or "sqlbuild")
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
        for key in ("path", "target", "description", "columns", "language", "return_kind"):
            if key in node:
                metadata[key] = node[key]
        return metadata

    def get_description(self, node: Mapping[str, Any]) -> str | None:
        value: object = node.get("description")
        return str(value) if value is not None else None

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


def _normalize_name(value: str) -> str:
    normalized: str = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return normalized or "check"
