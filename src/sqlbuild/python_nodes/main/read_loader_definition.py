"""Read SQLBuild loader metadata from a Python function."""

from collections.abc import Callable

from sqlbuild.python_nodes._helpers.attachment import read_attached_definition
from sqlbuild.python_nodes.models import LoaderDefinition


def read_loader_definition(function: Callable[..., object]) -> LoaderDefinition | None:
    """Return SQLBuild loader metadata from a decorated function, if present."""

    return read_attached_definition(
        function=function,
        attribute_name="__sqlbuild_loader__",
        definition_type=LoaderDefinition,
    )
