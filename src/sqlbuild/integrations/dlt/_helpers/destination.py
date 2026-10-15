"""Build dlt destinations from SQLBuild adapter connection config."""

from __future__ import annotations

from sqlbuild._native import dlt_destination_arguments
from sqlbuild.integrations.dlt.exceptions import DltIntegrationError
from sqlbuild.integrations.dlt.models import DltDestinationConfig


def build_dlt_destination(
    *,
    adapter_name: str,
    connection_config: dict[str, object],
    destination_config: dict[str, object] | None = None,
    dataset_name: str | None,
) -> DltDestinationConfig:
    """Return a dlt destination object and dataset for a SQLBuild target."""

    try:
        import dlt.destinations as destinations
    except ImportError as error:
        raise DltIntegrationError(
            "This source uses dlt, but dlt is not installed. Install it with: "
            "pip install 'sqlbuild[dlt]'"
        ) from error

    factory, arguments, options, resolved_dataset_name = dlt_destination_arguments(
        adapter_name=adapter_name,
        connection_config=connection_config,
        destination_config=destination_config,
        dataset_name=dataset_name,
    )
    return DltDestinationConfig(
        destination=getattr(destinations, factory)(**arguments, **options),
        dataset_name=resolved_dataset_name,
    )
