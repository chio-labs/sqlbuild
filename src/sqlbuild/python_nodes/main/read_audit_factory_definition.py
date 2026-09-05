"""Read SQLBuild audit-factory metadata from a Python function."""

from collections.abc import Callable

from sqlbuild.python_nodes._helpers.attachment import read_attached_definition
from sqlbuild.python_nodes.models import AuditFactoryDefinition


def read_audit_factory_definition(
    function: Callable[..., object],
) -> AuditFactoryDefinition | None:
    """Return SQLBuild audit-factory metadata from a decorated function, if present."""

    return read_attached_definition(
        function=function,
        attribute_name="__sqlbuild_audit_factory__",
        definition_type=AuditFactoryDefinition,
    )
