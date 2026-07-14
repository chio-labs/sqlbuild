"""Enforce the supported dbt interop mode."""

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.helpers.cli.mode import enforce_dbt_interop_standard_mode as _enforce


def enforce_dbt_interop_standard_mode(*, discovered_inputs: DiscoveredProjectInputs) -> None:
    """Reject dbt interop in virtual environment mode."""

    _ = _enforce(discovered_inputs=discovered_inputs)
