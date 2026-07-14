"""Rivers asset definitions for SQLBuild projects."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from sqlbuild.integrations.rivers._helpers.assets import build_asset_defs
from sqlbuild.integrations.rivers._helpers.dag import load_sqlbuild_dag
from sqlbuild.integrations.rivers._helpers.imports import load_rivers
from sqlbuild.integrations.rivers.exceptions import RiversDagInputError
from sqlbuild.integrations.rivers.project import SqlBuildProject
from sqlbuild.integrations.rivers.translator import SqlBuildRiversTranslator
from sqlbuild.integrations.rivers.types import SqlBuildDagInput

_DEFAULT_DAG_PATH: Path = Path("target/sqlbuild_dag.json")


def sqlbuild_assets(
    *,
    dag: SqlBuildDagInput | None = None,
    project: SqlBuildProject | None = None,
    translator: SqlBuildRiversTranslator | None = None,
    name: str | None = None,
) -> Callable[[Callable[..., Any]], Any]:
    """Create a Rivers multi-asset definition from a SQLBuild DAG artifact."""

    rs: Any = load_rivers()
    if dag is not None and project is not None:
        raise RiversDagInputError(
            "sqlbuild_assets received both 'dag' and 'project'; pass only one"
        )
    dag_input: SqlBuildDagInput = (
        dag if dag is not None else project.dag_path if project is not None else _DEFAULT_DAG_PATH
    )
    resolved_dag: Mapping[str, Any] = load_sqlbuild_dag(dag_input)
    resolved_translator: SqlBuildRiversTranslator = translator or SqlBuildRiversTranslator()
    output_defs: tuple[Any, ...] = build_asset_defs(
        dag=resolved_dag,
        translator=resolved_translator,
    )

    def decorator(fn: Callable[..., Any]) -> Any:
        return rs.Asset.from_multi(
            name=name,
            output_defs=list(output_defs),
        )(fn)

    return decorator
