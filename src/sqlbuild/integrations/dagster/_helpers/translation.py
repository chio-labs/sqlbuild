"""Runtime projection of SQLBuild DAG records through a Dagster translator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild.integrations.dagster.classes.sqlbuild_dagster_translator import (
    SqlBuildDagsterTranslator,
)
from sqlbuild.integrations.dagster.constants import (
    DAGSTER_ASSET_ENABLED_FIELD,
    DAGSTER_CHECK_ENABLED_FIELD,
    DAGSTER_CHECK_NAME_FIELD,
)


def translate_sqlbuild_dag(
    *, dag: Mapping[str, Any], translator: SqlBuildDagsterTranslator
) -> Mapping[str, Any]:
    """Return an in-memory DAG whose runtime identities match its static Dagster specs."""

    project_name: object = dag.get("project_name")
    translated_nodes: list[dict[str, Any]] = []
    for node in dag.get("nodes", ()):
        translated_node: dict[str, Any] = {**node, "project_name": project_name}
        asset_enabled: bool = translator.is_asset_node(translated_node)
        asset_key: Any = translator.get_asset_key(translated_node)
        translated_node["asset_key"] = [str(part) for part in asset_key.path]
        translated_node[DAGSTER_ASSET_ENABLED_FIELD] = asset_enabled
        translated_nodes.append(translated_node)

    translated_checks: list[dict[str, Any]] = []
    for check in dag.get("checks", ()):
        translated_checks.append(
            {
                **check,
                DAGSTER_CHECK_NAME_FIELD: translator.get_check_name(check),
                DAGSTER_CHECK_ENABLED_FIELD: translator.is_asset_check(check),
            }
        )

    return {**dag, "nodes": translated_nodes, "checks": translated_checks}


def is_dagster_asset_enabled(node: Mapping[str, Any]) -> bool:
    """Return whether a translated DAG node is owned by the SQLBuild asset definition."""

    return bool(node.get(DAGSTER_ASSET_ENABLED_FIELD, True))


def is_dagster_check_enabled(check: Mapping[str, Any]) -> bool:
    """Return whether a translated DAG check is owned by the SQLBuild asset definition."""

    return bool(check.get(DAGSTER_CHECK_ENABLED_FIELD, True))
