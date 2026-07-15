"""Definition attachment and reading for Python-node functions."""

from collections.abc import Callable
from typing import Any, cast


def attach_definition(
    *, function: Callable[..., object], attribute_name: str, definition: object
) -> Callable[..., object]:
    authoring_function: Any = cast(Any, function)
    setattr(authoring_function, attribute_name, definition)
    return function


def read_attached_definition[DefinitionT](
    *,
    function: Callable[..., object],
    attribute_name: str,
    definition_type: type[DefinitionT],
) -> DefinitionT | None:
    value: Any = getattr(function, attribute_name, None)
    return value if isinstance(value, definition_type) else None
