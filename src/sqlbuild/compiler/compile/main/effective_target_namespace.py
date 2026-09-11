"""Public effective target namespace operation."""

from sqlbuild.compiler.compile._helpers.attachment.target import (
    build_effective_target_namespace as _build_effective_target_namespace,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import TargetConfig


def build_effective_target_namespace(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    connection_database: object | None,
    connection_schema: object | None,
    default_database: str | None,
    default_schema: str | None,
) -> tuple[str | None, TargetConfig | None, str | None, str | None]:
    """Resolve the target and its effective database/schema without compiling resources."""

    return _build_effective_target_namespace(
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
        connection_database=connection_database,
        connection_schema=connection_schema,
        default_database=default_database,
        default_schema=default_schema,
    )
