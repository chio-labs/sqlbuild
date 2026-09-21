"""Attach typed metadata to a Python-node function."""

from collections.abc import Callable

from sqlbuild.python_nodes._helpers.attachment import attach_definition as _attach_definition


def attach_definition(
    *, function: Callable[..., object], attribute_name: str, definition: object
) -> Callable[..., object]:
    """Attach one typed definition to an authoring function."""

    return _attach_definition(
        function=function,
        attribute_name=attribute_name,
        definition=definition,
    )
