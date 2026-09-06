"""Dagster asset selection backed by a SQLBuild DAG artifact."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

from sqlbuild.compiler.planner.main.selection.selector_parse import parse_project_selector
from sqlbuild.compiler.planner.models import ParsedSelector, PathSelector
from sqlbuild.compiler.planner.types import SelectorKind
from sqlbuild.integrations.dagster._helpers.dag import load_sqlbuild_dag
from sqlbuild.integrations.dagster._helpers.imports import load_dagster
from sqlbuild.integrations.dagster.classes.sqlbuild_dagster_translator import (
    SqlBuildDagsterTranslator,
)
from sqlbuild.integrations.dagster.constants import DAGSTER_ASSET_NODE_KINDS
from sqlbuild.integrations.dagster.exceptions import DagsterDagInputError
from sqlbuild.integrations.dagster.types import SqlBuildDagInput


def build_sqlbuild_asset_selection_impl(
    *,
    sqlbuild_assets: Sequence[Any],
    dag: SqlBuildDagInput,
    sqlbuild_select: str,
    sqlbuild_exclude: str | None = None,
    translator: SqlBuildDagsterTranslator | None = None,
) -> Any:
    """Resolve canonical SQLBuild selectors into a Dagster asset selection."""

    if not sqlbuild_assets:
        raise DagsterDagInputError("SQLBuild asset selection requires an asset definition")
    resolved_dag: Mapping[str, Any] = load_sqlbuild_dag(dag)
    resolved_translator: SqlBuildDagsterTranslator = translator or SqlBuildDagsterTranslator()
    selected_ids: set[str] = _resolve_dag_selectors(
        dag=resolved_dag,
        select=sqlbuild_select,
        exclude=sqlbuild_exclude,
    )
    asset_keys: list[Any] = []
    project_name: object = resolved_dag.get("project_name")
    for node in resolved_dag.get("nodes", ()):
        if str(node.get("id")) not in selected_ids:
            continue
        if str(node.get("kind")) not in DAGSTER_ASSET_NODE_KINDS:
            continue
        translated_node: Mapping[str, Any] = {**node, "project_name": project_name}
        if not resolved_translator.is_asset_node(translated_node):
            continue
        asset_keys.append(resolved_translator.get_asset_key(translated_node))
    return load_dagster().AssetSelection.assets(*asset_keys)


def _resolve_dag_selectors(*, dag: Mapping[str, Any], select: str, exclude: str | None) -> set[str]:
    nodes_by_id: dict[str, Mapping[str, Any]] = {
        str(node["id"]): node for node in dag.get("nodes", ())
    }
    upstream, downstream = _dependency_indexes(dag=dag, node_ids=set(nodes_by_id))
    selected: set[str] = _resolve_expression(
        expression=select,
        dag=dag,
        nodes_by_id=nodes_by_id,
        upstream=upstream,
        downstream=downstream,
    )
    if exclude:
        selected.difference_update(
            _resolve_expression(
                expression=exclude,
                dag=dag,
                nodes_by_id=nodes_by_id,
                upstream=upstream,
                downstream=downstream,
            )
        )
    return selected


def _resolve_expression(
    *,
    expression: str,
    dag: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    upstream: Mapping[str, set[str]],
    downstream: Mapping[str, set[str]],
) -> set[str]:
    selected: set[str] = set()
    for token in expression.split():
        intersections: list[set[str]] = [
            _resolve_atomic(
                raw=part,
                dag=dag,
                nodes_by_id=nodes_by_id,
                upstream=upstream,
                downstream=downstream,
            )
            for part in token.split(",")
        ]
        token_selection: set[str] = intersections[0]
        for intersection in intersections[1:]:
            token_selection.intersection_update(intersection)
        selected.update(token_selection)
    return selected


def _resolve_atomic(
    *,
    raw: str,
    dag: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    upstream: Mapping[str, set[str]],
    downstream: Mapping[str, set[str]],
) -> set[str]:
    parsed: ParsedSelector | PathSelector = parse_project_selector(raw)
    if isinstance(parsed, PathSelector):
        start_id: str = _node_id_for_name(nodes_by_id=nodes_by_id, name=parsed.start_name)
        end_id: str = _node_id_for_name(nodes_by_id=nodes_by_id, name=parsed.end_name)
        matched: set[str] = _shortest_path(start_id=start_id, end_id=end_id, downstream=downstream)
        if parsed.upstream:
            matched.update(_expand(start_ids={start_id}, adjacency=upstream))
        if parsed.downstream:
            matched.update(_expand(start_ids={end_id}, adjacency=downstream))
        return matched

    matched = _match_parsed_selector(parsed=parsed, dag=dag, nodes_by_id=nodes_by_id)
    if parsed.upstream:
        matched.update(_expand(start_ids=matched, adjacency=upstream))
    if parsed.downstream:
        matched.update(_expand(start_ids=matched, adjacency=downstream))
    return matched


def _match_parsed_selector(
    *,
    parsed: ParsedSelector,
    dag: Mapping[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    if parsed.kind == SelectorKind.TAG:
        return {
            node_id
            for node_id, node in nodes_by_id.items()
            if _node_has_tag(node=node, tag=parsed.value)
        }
    if parsed.kind == SelectorKind.PATH:
        folder: str = parsed.value.replace("\\", "/").strip("/")
        return {
            node_id
            for node_id, node in nodes_by_id.items()
            if _path_is_under(path=node.get("path"), folder=folder)
        }
    if parsed.kind == SelectorKind.CHECK:
        checked_ids: set[str] = set()
        for check in dag.get("checks", ()):
            if str(check.get("name")) == parsed.value or str(check.get("id")) == parsed.value:
                checked_ids.update(str(asset_id) for asset_id in check.get("checked_asset_ids", ()))
        return checked_ids
    expected_kind: str | None = None if parsed.kind == SelectorKind.NAME else str(parsed.kind.value)
    return {
        node_id
        for node_id, node in nodes_by_id.items()
        if str(node.get("name")) == parsed.value
        and (expected_kind is None or str(node.get("kind")) == expected_kind)
    }


def _node_has_tag(*, node: Mapping[str, Any], tag: str) -> bool:
    return any(str(node_tag) == tag for node_tag in node.get("tags", ()))


def _path_is_under(*, path: object, folder: str) -> bool:
    if not isinstance(path, str):
        return False
    normalized_path: str = path.replace("\\", "/").strip("/")
    candidates: tuple[str, ...] = (
        folder,
        f"models/{folder}" if folder and not folder.startswith("models/") else folder,
    )
    return any(
        normalized_path == candidate or normalized_path.startswith(f"{candidate}/")
        for candidate in candidates
        if candidate
    )


def _dependency_indexes(
    *, dag: Mapping[str, Any], node_ids: set[str]
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    upstream: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    downstream: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in dag.get("edges", ()):
        from_id: str = str(edge.get("from_id"))
        to_id: str = str(edge.get("to_id"))
        if from_id not in node_ids or to_id not in node_ids:
            continue
        upstream[to_id].add(from_id)
        downstream[from_id].add(to_id)
    return upstream, downstream


def _expand(*, start_ids: set[str], adjacency: Mapping[str, set[str]]) -> set[str]:
    expanded: set[str] = set(start_ids)
    pending: list[str] = list(start_ids)
    while pending:
        node_id: str = pending.pop()
        for adjacent_id in adjacency.get(node_id, set()):
            if adjacent_id in expanded:
                continue
            expanded.add(adjacent_id)
            pending.append(adjacent_id)
    return expanded


def _node_id_for_name(*, nodes_by_id: Mapping[str, Mapping[str, Any]], name: str) -> str:
    matching_ids: list[str] = [
        node_id for node_id, node in nodes_by_id.items() if str(node.get("name")) == name
    ]
    if len(matching_ids) != 1:
        raise DagsterDagInputError(
            f"SQLBuild selector name {name!r} matched {len(matching_ids)} DAG nodes"
        )
    return matching_ids[0]


def _shortest_path(*, start_id: str, end_id: str, downstream: Mapping[str, set[str]]) -> set[str]:
    pending: deque[tuple[str, tuple[str, ...]]] = deque([(start_id, (start_id,))])
    visited: set[str] = {start_id}
    while pending:
        node_id, path = pending.popleft()
        if node_id == end_id:
            return set(path)
        for adjacent_id in downstream.get(node_id, set()):
            if adjacent_id in visited:
                continue
            visited.add(adjacent_id)
            pending.append((adjacent_id, (*path, adjacent_id)))
    raise DagsterDagInputError(f"no SQLBuild DAG path exists between {start_id!r} and {end_id!r}")
