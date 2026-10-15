"""Dagster AssetSpec and AssetCheckSpec builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild._native import dagster_asset_plans, dagster_check_plans
from sqlbuild.integrations.dagster._helpers.imports import load_dagster
from sqlbuild.integrations.dagster.classes.sqlbuild_dagster_translator import (
    SqlBuildDagsterTranslator,
)


def build_asset_specs(
    *, dag: Mapping[str, Any], translator: SqlBuildDagsterTranslator
) -> tuple[Any, ...]:
    """Build materializable Dagster asset specs from a SQLBuild DAG artifact."""

    dg: Any = load_dagster()
    specs: list[Any] = []
    for translated_node, upstream_nodes, kinds in dagster_asset_plans(dag):
        if not translator.is_asset_node(translated_node):
            continue
        deps: list[Any] = [
            dg.AssetDep(translator.get_asset_key(upstream_node)) for upstream_node in upstream_nodes
        ]
        specs.append(
            dg.AssetSpec(
                key=translator.get_asset_key(translated_node),
                deps=deps,
                description=translator.get_description(translated_node),
                group_name=translator.get_group_name(translated_node),
                metadata=translator.get_metadata(translated_node),
                tags=translator.get_tags(translated_node),
                kinds=kinds,
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

    return _build_check_specs(
        plans=dagster_check_plans(dag, include_scenarios=include_scenarios, only_scenarios=False),
        translator=translator,
    )


def build_scenario_check_specs(
    *, dag: Mapping[str, Any], translator: SqlBuildDagsterTranslator
) -> tuple[Any, ...]:
    """Build Dagster check specs for SQLBuild scenario checks only."""

    return _build_check_specs(
        plans=dagster_check_plans(dag, include_scenarios=True, only_scenarios=True),
        translator=translator,
    )


def _build_check_specs(
    *,
    plans: list[tuple[Mapping[str, Any], bool, list[Mapping[str, Any]], str | None]],
    translator: SqlBuildDagsterTranslator,
) -> tuple[Any, ...]:
    dg: Any = load_dagster()
    specs: list[Any] = []
    for check, included, checked_nodes, description in plans:
        if not translator.is_asset_check(check) or not included:
            continue
        for node in checked_nodes:
            if not translator.is_asset_node(node):
                continue
            specs.append(
                dg.AssetCheckSpec(
                    name=translator.get_check_name(check),
                    asset=translator.get_asset_key(node),
                    description=description,
                    metadata=translator.get_check_metadata(check),
                )
            )
    return tuple(specs)
