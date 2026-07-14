"""Rivers AssetDef builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild.integrations.rivers._helpers.imports import load_rivers
from sqlbuild.integrations.rivers.translator import SqlBuildRiversTranslator

_ASSET_KINDS: frozenset[str] = frozenset(
    {"source", "loader", "seed", "model", "udf", "table_fn", "task", "asset"}
)


def build_asset_defs(
    *, dag: Mapping[str, Any], translator: SqlBuildRiversTranslator
) -> tuple[Any, ...]:
    """Build materializable Rivers asset definitions from a SQLBuild DAG artifact."""

    rs: Any = load_rivers()
    nodes_by_id: dict[str, Mapping[str, Any]] = _nodes_by_id(dag)
    upstream_by_id: dict[str, list[str]] = _upstream_by_id(dag)
    project_name: object = dag.get("project_name")
    asset_defs: list[Any] = []
    for node in dag["nodes"]:
        if str(node.get("kind")) not in _ASSET_KINDS:
            continue
        translated_node: Mapping[str, Any] = {**node, "project_name": project_name}
        deps: list[Any] = []
        for upstream_id in upstream_by_id.get(str(node["id"]), []):
            upstream_node: Mapping[str, Any] | None = nodes_by_id.get(upstream_id)
            if upstream_node is None or str(upstream_node.get("kind")) not in _ASSET_KINDS:
                continue
            deps.append(rs.AssetDef.dep(translator.get_asset_name(upstream_node)))
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


def _nodes_by_id(dag: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(node["id"]): node for node in dag["nodes"]}


def _upstream_by_id(dag: Mapping[str, Any]) -> dict[str, list[str]]:
    upstream: dict[str, list[str]] = {}
    edge: Mapping[str, Any]
    for edge in dag["edges"]:
        upstream.setdefault(str(edge["to_id"]), []).append(str(edge["from_id"]))
    return upstream
