"""Dagster scenario check definition decorator for SQLBuild projects."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from sqlbuild.integrations.dagster._helpers.assets import build_scenario_check_specs
from sqlbuild.integrations.dagster._helpers.dag import load_sqlbuild_dag
from sqlbuild.integrations.dagster._helpers.imports import load_dagster
from sqlbuild.integrations.dagster.classes.sqlbuild_dagster_translator import (
    SqlBuildDagsterTranslator,
)
from sqlbuild.integrations.dagster.exceptions import DagsterDagInputError
from sqlbuild.integrations.dagster.models import SqlBuildProject
from sqlbuild.integrations.dagster.types import SqlBuildDagInput


def sqlbuild_scenario_checks(
    *,
    dag: SqlBuildDagInput | None = None,
    project: SqlBuildProject | None = None,
    translator: SqlBuildDagsterTranslator | None = None,
    name: str | None = None,
    required_resource_keys: set[str] | None = None,
) -> Callable[[Callable[..., Any]], Any]:
    """Create a Dagster multi-asset-check definition for SQLBuild scenarios."""

    dg: Any = load_dagster()
    if dag is not None and project is not None:
        raise DagsterDagInputError(
            "sqlbuild_scenario_checks received both 'dag' and 'project'; pass only one"
        )
    dag_input: SqlBuildDagInput = (
        dag
        if dag is not None
        else project.dag_path
        if project is not None
        else Path("target/sqlbuild_dag.json")
    )
    resolved_dag: Mapping[str, Any] = load_sqlbuild_dag(dag_input)
    resolved_translator: SqlBuildDagsterTranslator = translator or SqlBuildDagsterTranslator()
    check_specs: tuple[Any, ...] = build_scenario_check_specs(
        dag=resolved_dag,
        translator=resolved_translator,
    )

    def decorator(fn: Callable[..., Any]) -> Any:
        return dg.multi_asset_check(
            name=name,
            specs=check_specs,
            can_subset=True,
            required_resource_keys=required_resource_keys,
        )(fn)

    return decorator
