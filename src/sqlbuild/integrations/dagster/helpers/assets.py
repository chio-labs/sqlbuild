"""Dagster AssetSpec and AssetCheckSpec builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild.integrations.dagster.helpers.imports import load_dagster
from sqlbuild.integrations.dagster.translator import SqlBuildDagsterTranslator

_ASSET_KINDS: frozenset[str] = frozenset({"source", "seed", "model", "function"})


def build_asset_specs(
    *, dag: Mapping[str, Any], translator: SqlBuildDagsterTranslator
) -> tuple[Any, ...]:
    """Build materializable Dagster asset specs from a SQLBuild DAG artifact."""

    dg: Any = load_dagster()
    nodes_by_id: dict[str, Mapping[str, Any]] = _nodes_by_id(dag)
    upstream_by_id: dict[str, list[str]] = _upstream_by_id(dag)
    project_name: object = dag.get("project_name")
    specs: list[Any] = []
    for node in dag["nodes"]:
        if str(node.get("kind")) not in _ASSET_KINDS:
            continue
        translated_node: Mapping[str, Any] = {**node, "project_name": project_name}
        deps: list[Any] = []
        for upstream_id in upstream_by_id.get(str(node["id"]), []):
            upstream_node: Mapping[str, Any] | None = nodes_by_id.get(upstream_id)
            if upstream_node is None:
                continue
            deps.append(dg.AssetDep(translator.get_asset_key(upstream_node)))
        specs.append(
            dg.AssetSpec(
                key=translator.get_asset_key(translated_node),
                deps=deps,
                description=translator.get_description(translated_node),
                group_name=translator.get_group_name(translated_node),
                metadata=translator.get_metadata(translated_node),
                tags=translator.get_tags(translated_node),
                kinds=_asset_spec_kinds(translated_node),
            )
        )
    return tuple(specs)


def build_check_specs(
    *,
    dag: Mapping[str, Any],
    translator: SqlBuildDagsterTranslator,
    include_scenarios: bool = True,
) -> tuple[Any, ...]:
    """Build Dagster check specs from SQLBuild test/audit/scenario checks."""

    excluded_kinds: set[str] = set() if include_scenarios else {"scenario"}
    return _build_check_specs(
        dag=dag,
        translator=translator,
        kinds=None,
        excluded_kinds=excluded_kinds,
    )


def build_scenario_check_specs(
    *, dag: Mapping[str, Any], translator: SqlBuildDagsterTranslator
) -> tuple[Any, ...]:
    """Build Dagster check specs for SQLBuild scenario checks only."""

    return _build_check_specs(
        dag=dag,
        translator=translator,
        kinds={"scenario"},
        excluded_kinds=set(),
    )


def _build_check_specs(
    *,
    dag: Mapping[str, Any],
    translator: SqlBuildDagsterTranslator,
    kinds: set[str] | None,
    excluded_kinds: set[str],
) -> tuple[Any, ...]:
    """Build Dagster check specs from SQLBuild checks matching optional kinds."""

    dg: Any = load_dagster()
    nodes_by_id: dict[str, Mapping[str, Any]] = _nodes_by_id(dag)
    specs: list[Any] = []
    for check in dag["checks"]:
        check_kind: str = str(check.get("kind"))
        if check_kind in excluded_kinds:
            continue
        if kinds is not None and check_kind not in kinds:
            continue
        for asset_id in check.get("checked_asset_ids", ()):
            node: Mapping[str, Any] | None = nodes_by_id.get(str(asset_id))
            if node is None:
                continue
            specs.append(
                dg.AssetCheckSpec(
                    name=translator.get_check_name(check),
                    asset=translator.get_asset_key(node),
                    description=str(check.get("path")) if check.get("path") is not None else None,
                    metadata=translator.get_check_metadata(check),
                )
            )
    return tuple(specs)


def _nodes_by_id(dag: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(node["id"]): node for node in dag["nodes"]}


def _upstream_by_id(dag: Mapping[str, Any]) -> dict[str, list[str]]:
    upstream: dict[str, list[str]] = {}
    edge: Mapping[str, Any]
    for edge in dag["edges"]:
        upstream.setdefault(str(edge["to_id"]), []).append(str(edge["from_id"]))
    return upstream


def _asset_spec_kinds(node: Mapping[str, Any]) -> set[str]:
    kind: str = str(node.get("kind"))
    if kind == "model":
        materialization_type: str = str(node.get("materialization_type") or "table")
        if materialization_type == "view":
            return {"sqlbuild", "view"}
        return {"sqlbuild", "table"}
    if kind in {"source", "seed"}:
        return {"sqlbuild", kind}
    if kind == "function":
        return {"sqlbuild", "function"}
    return {"sqlbuild"}
