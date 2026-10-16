"""SQLBuild-to-Dagster translation hooks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild._native import (
    dagster_default_asset_key_path,
    dagster_default_check_metadata,
    dagster_default_check_name,
    dagster_default_description,
    dagster_default_group_name,
    dagster_default_metadata,
    dagster_default_tags,
)
from sqlbuild.integrations.dagster._helpers.imports import load_dagster


class SqlBuildDagsterTranslator:
    """Default mapping from SQLBuild DAG records to Dagster metadata."""

    def get_asset_key(self, node: Mapping[str, Any]) -> Any:
        dg: Any = load_dagster()
        return dg.AssetKey(dagster_default_asset_key_path(node))

    def is_asset_node(self, node: Mapping[str, Any]) -> bool:
        """Return whether SQLBuild owns this node as a Dagster asset."""

        return True

    def is_asset_check(self, check: Mapping[str, Any]) -> bool:
        """Return whether SQLBuild exposes this check through the multi-asset definition."""

        return True

    def get_group_name(self, node: Mapping[str, Any]) -> str | None:
        return dagster_default_group_name(node)

    def get_tags(self, node: Mapping[str, Any]) -> Mapping[str, str]:
        return dagster_default_tags(node)

    def get_metadata(self, node: Mapping[str, Any]) -> Mapping[str, Any]:
        return dagster_default_metadata(node)

    def get_description(self, node: Mapping[str, Any]) -> str | None:
        return dagster_default_description(node)

    def get_check_name(self, check: Mapping[str, Any]) -> str:
        return dagster_default_check_name(check)

    def get_check_metadata(self, check: Mapping[str, Any]) -> Mapping[str, Any]:
        return dagster_default_check_metadata(check)
