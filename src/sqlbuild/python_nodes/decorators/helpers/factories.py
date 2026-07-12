"""Decorator implementation for SQLBuild Python-node factories."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from sqlbuild.python_nodes.models import FactoryDefinition


def factory(
    function: Callable[..., object],
) -> Callable[..., object]:
    """Mark a Python function as a SQLBuild Python-node factory."""

    factory_function: Any = cast(Any, function)
    factory_function.__sqlbuild_factory__ = FactoryDefinition(name=factory_function.__name__)
    return function


def get_factory_definition(function: Callable[..., object]) -> FactoryDefinition | None:
    """Return SQLBuild factory metadata from a decorated function, if present."""

    value: Any = getattr(function, "__sqlbuild_factory__", None)
    if isinstance(value, FactoryDefinition):
        return value
    return None
