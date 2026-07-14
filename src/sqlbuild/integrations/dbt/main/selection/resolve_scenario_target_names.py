"""Resolve dbt scenario target names."""

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt._helpers.selection.sql_test_targets import (
    resolve_dbt_scenario_target_names as _resolve,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex


def resolve_dbt_scenario_target_names(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    selected_dbt_unique_ids: tuple[str, ...],
    select: tuple[str, ...],
) -> tuple[str, ...]:
    """Return dbt models targeted by selected scenarios."""

    return _resolve(
        project=project,
        manifest=manifest,
        selected_dbt_unique_ids=selected_dbt_unique_ids,
        select=select,
    )
