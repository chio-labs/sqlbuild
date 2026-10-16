"""Dependency declaration normalization for Python-node decorators."""

from collections.abc import Callable

from sqlbuild.python_nodes.models import SqlResourceRef


def normalize_python_node_dependencies(
    value: Callable[..., object]
    | SqlResourceRef
    | tuple[Callable[..., object] | SqlResourceRef, ...]
    | list[Callable[..., object] | SqlResourceRef],
) -> tuple[Callable[..., object] | SqlResourceRef, ...]:
    if callable(value) or isinstance(value, SqlResourceRef):
        return (value,)
    return tuple(value)


def normalize_loader_dependencies(
    value: tuple[Callable[..., object], ...] | list[Callable[..., object]],
) -> tuple[Callable[..., object], ...]:
    return tuple(value)
