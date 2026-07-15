"""Read SQLBuild task metadata from a Python function."""

from collections.abc import Callable

from sqlbuild.python_nodes._helpers.attachment import read_attached_definition
from sqlbuild.python_nodes.models import TaskDefinition


def read_task_definition(function: Callable[..., object]) -> TaskDefinition | None:
    """Return SQLBuild task metadata from a decorated function, if present."""

    return read_attached_definition(
        function=function,
        attribute_name="__sqlbuild_task__",
        definition_type=TaskDefinition,
    )
