"""Read audit-factory declarations."""

from collections.abc import Callable

from sqlbuild.python_nodes.main.read_audit_factory_definition import (
    read_audit_factory_definition,
)
from sqlbuild.python_nodes.models import AuditFactoryDefinition


def get_audit_factory_definition(
    function: Callable[..., object],
) -> AuditFactoryDefinition | None:
    """Return audit-factory metadata from a decorated function, if present."""

    return read_audit_factory_definition(function)
