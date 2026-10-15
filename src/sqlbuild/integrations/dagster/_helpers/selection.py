"""Dagster asset selection backed by a SQLBuild DAG artifact."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlbuild._native import load_sqlbuild_dag, resolve_dag_selection
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
    resolved_dag: Mapping[str, Any] = load_sqlbuild_dag(dag, error_class=DagsterDagInputError)
    resolved_translator: SqlBuildDagsterTranslator = translator or SqlBuildDagsterTranslator()
    selected_ids: frozenset[str] = resolve_dag_selection(
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
