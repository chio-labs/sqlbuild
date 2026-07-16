"""Apply SQLBuild lifecycle-hook metadata to a Python function."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from sqlbuild.python_nodes._helpers.attachment import attach_definition
from sqlbuild.python_nodes._helpers.description_resolution import resolve_description
from sqlbuild.python_nodes.models import HookDefinition


def apply_hook(
    *,
    function: Callable[..., object] | None = None,
    name: str | None = None,
    description: str | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Apply SQLBuild lifecycle-hook metadata to a Python function."""

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        inner_function: Any = cast(Any, inner)
        definition: HookDefinition = HookDefinition(
            name=name or inner_function.__name__,
            description=resolve_description(function=inner, description=description),
        )
        return attach_definition(
            function=inner,
            attribute_name="__sqlbuild_hook__",
            definition=definition,
        )

    return decorate(function) if function is not None else decorate
