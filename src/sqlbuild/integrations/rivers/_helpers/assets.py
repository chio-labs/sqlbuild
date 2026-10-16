"""Rivers AssetDef builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild._native import rivers_asset_plans
from sqlbuild.integrations.rivers._helpers.imports import load_rivers
from sqlbuild.integrations.rivers.classes.sqlbuild_rivers_translator import (
    SqlBuildRiversTranslator,
)


def build_asset_defs(
    *, dag: Mapping[str, Any], translator: SqlBuildRiversTranslator
) -> tuple[Any, ...]:
    """Build materializable Rivers asset definitions from a SQLBuild DAG artifact."""

    rs: Any = load_rivers()
    asset_defs: list[Any] = []
    for translated_node, upstream_nodes in rivers_asset_plans(dag):
        deps: list[Any] = [
            rs.AssetDef.dep(translator.get_asset_name(upstream_node))
            for upstream_node in upstream_nodes
        ]
        asset_defs.append(
            rs.AssetDef(
                name=translator.get_asset_name(translated_node),
                tags=translator.get_tags(translated_node),
                kinds=translator.get_kinds(translated_node),
                group=translator.get_group_name(translated_node),
                metadata=translator.get_metadata(translated_node),
                deps=deps,
            )
        )
    return tuple(asset_defs)
