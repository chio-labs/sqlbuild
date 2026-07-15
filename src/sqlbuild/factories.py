"""Public decorator API for SQLBuild Python-node factories."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.python_nodes.main.apply_factory import apply_factory
from sqlbuild.python_nodes.main.read_factory_definition import read_factory_definition
from sqlbuild.python_nodes.models import FactoryDefinition

__all__ = ("factory", "get_factory_definition")


def factory(
    function: Callable[..., object],
) -> Callable[..., object]:
    """Mark a Python function as a SQLBuild Python-node factory."""

    return apply_factory(function)


def get_factory_definition(function: Callable[..., object]) -> FactoryDefinition | None:
    """Return SQLBuild factory metadata from a decorated function, if present."""

    return read_factory_definition(function)
