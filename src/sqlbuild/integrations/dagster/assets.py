"""Dagster asset definition decorators for SQLBuild projects."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from sqlbuild.integrations.dagster.helpers.assets import build_asset_specs, build_check_specs
from sqlbuild.integrations.dagster.helpers.dag import load_sqlbuild_dag
from sqlbuild.integrations.dagster.helpers.imports import load_dagster
from sqlbuild.integrations.dagster.translator import SqlBuildDagsterTranslator
from sqlbuild.integrations.dagster.types import SqlBuildDagInput

_DEFAULT_DAG_PATH: Path = Path("target/sqlbuild_dag.json")


def sqlbuild_assets(
    *,
    dag: SqlBuildDagInput = _DEFAULT_DAG_PATH,
    translator: SqlBuildDagsterTranslator | None = None,
    name: str | None = None,
    required_resource_keys: set[str] | None = None,
) -> Callable[[Callable[..., Any]], Any]:
    """Create a Dagster multi-asset definition from a SQLBuild DAG artifact."""

    dg: Any = load_dagster()
    resolved_dag: Mapping[str, Any] = load_sqlbuild_dag(dag)
    resolved_translator: SqlBuildDagsterTranslator = translator or SqlBuildDagsterTranslator()
    specs: tuple[Any, ...] = build_asset_specs(
        dag=resolved_dag,
        translator=resolved_translator,
    )
    check_specs: tuple[Any, ...] = build_check_specs(
        dag=resolved_dag,
        translator=resolved_translator,
    )

    def decorator(fn: Callable[..., Any]) -> Any:
        return dg.multi_asset(
            name=name,
            specs=specs,
            check_specs=check_specs,
            can_subset=True,
            required_resource_keys=required_resource_keys,
        )(fn)

    return decorator
