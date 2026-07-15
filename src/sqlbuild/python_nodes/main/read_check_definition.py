"""Read SQLBuild check metadata from a Python function."""

from collections.abc import Callable

from sqlbuild.python_nodes._helpers.attachment import read_attached_definition
from sqlbuild.python_nodes.models import CheckDefinition


def read_check_definition(function: Callable[..., object]) -> CheckDefinition | None:
    """Return SQLBuild check metadata from a decorated function, if present."""

    return read_attached_definition(
        function=function,
        attribute_name="__sqlbuild_check__",
        definition_type=CheckDefinition,
    )
