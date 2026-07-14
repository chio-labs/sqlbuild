"""Resolve dbt plan options."""

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.helpers.planning.runtime import resolve_dbt_plan_options as _resolve
from sqlbuild.integrations.dbt.models import DbtCliOptions


def resolve_dbt_plan_options(
    *, project_dir: Path, discovered_inputs: DiscoveredProjectInputs, dbt_args: tuple[str, ...]
) -> DbtCliOptions:
    """Resolve dbt CLI options for interop planning."""

    return _resolve(project_dir=project_dir, discovered_inputs=discovered_inputs, dbt_args=dbt_args)
