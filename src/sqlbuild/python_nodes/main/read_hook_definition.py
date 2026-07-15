"""Read SQLBuild lifecycle-hook metadata from a Python function."""

from collections.abc import Callable

from sqlbuild.python_nodes._helpers.attachment import read_attached_definition
from sqlbuild.python_nodes.models import HookDefinition


def read_hook_definition(function: Callable[..., object]) -> HookDefinition | None:
    """Return SQLBuild hook metadata from a decorated function, if present."""

    return read_attached_definition(
        function=function,
        attribute_name="__sqlbuild_hook__",
        definition_type=HookDefinition,
    )
