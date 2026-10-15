"""Dagster asset selection backed by a SQLBuild DAG artifact."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlbuild._native import dagster_selected_asset_nodes, load_sqlbuild_dag
from sqlbuild.integrations.dagster._helpers.imports import load_dagster
from sqlbuild.integrations.dagster.classes.sqlbuild_dagster_translator import (
    SqlBuildDagsterTranslator,
)
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
    asset_keys: list[Any] = [
        resolved_translator.get_asset_key(node)
        for node in dagster_selected_asset_nodes(
            resolved_dag, select=sqlbuild_select, exclude=sqlbuild_exclude
        )
        if resolved_translator.is_asset_node(node)
    ]
    return load_dagster().AssetSelection.assets(*asset_keys)
