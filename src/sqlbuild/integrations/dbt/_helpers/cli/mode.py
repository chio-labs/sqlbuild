"""dbt interop mode guard helpers."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError


def enforce_dbt_interop_direct_mode(*, discovered_inputs: DiscoveredProjectInputs) -> None:
    """Block dbt interop commands in virtual environment mode."""

    if discovered_inputs.project_config.settings.virtual_environments:
        raise DbtInteropConfigError(
            "sqb dbt is not supported when virtual_environments = true",
            code="C241",
            help="Disable virtual_environments or run dbt and SQLBuild virtual builds separately.",
        )
