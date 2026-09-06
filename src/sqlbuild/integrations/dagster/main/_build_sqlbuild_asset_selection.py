"""Public Dagster asset-selection entrypoint."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlbuild.integrations.dagster._helpers.selection import (
    build_sqlbuild_asset_selection_impl,
)
from sqlbuild.integrations.dagster.classes.sqlbuild_dagster_translator import (
    SqlBuildDagsterTranslator,
)
from sqlbuild.integrations.dagster.types import SqlBuildDagInput


def build_sqlbuild_asset_selection(
    *,
    sqlbuild_assets: Sequence[Any],
    dag: SqlBuildDagInput,
    sqlbuild_select: str,
    sqlbuild_exclude: str | None = None,
    translator: SqlBuildDagsterTranslator | None = None,
) -> Any:
    """Resolve canonical SQLBuild selectors into a Dagster asset selection."""

    return build_sqlbuild_asset_selection_impl(
        sqlbuild_assets=sqlbuild_assets,
        dag=dag,
        sqlbuild_select=sqlbuild_select,
        sqlbuild_exclude=sqlbuild_exclude,
        translator=translator,
    )
