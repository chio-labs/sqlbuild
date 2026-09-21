"""Read typed metadata from a Python-node function."""

from collections.abc import Callable

from sqlbuild.python_nodes._helpers.attachment import (
    read_attached_definition as _read_attached_definition,
)


def read_attached_definition[DefinitionT](
    *,
    function: Callable[..., object],
    attribute_name: str,
    definition_type: type[DefinitionT],
) -> DefinitionT | None:
    """Read one typed definition from an authoring function."""

    return _read_attached_definition(
        function=function,
        attribute_name=attribute_name,
        definition_type=definition_type,
    )
