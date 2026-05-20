"""Public decorator API for SQLBuild source loaders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast, overload

from sqlbuild.shared.models import LoaderDefinition


def _decorate_loader(
    function: Callable[..., object],
    *,
    depends_on: tuple[Callable[..., object], ...] = (),
    target: str | None = None,
) -> Callable[..., object]:
    loader_function: Any = cast(Any, function)
    definition: LoaderDefinition = LoaderDefinition(
        name=loader_function.__name__,
        depends_on=depends_on,
        target=target,
    )
    loader_function.__sqlbuild_loader__ = definition
    return function


@overload
def loader(function: Callable[..., object], /) -> Callable[..., object]: ...


@overload
def loader(
    *,
    depends_on: tuple[Callable[..., object], ...] | list[Callable[..., object]] = (),
    target: str | None = None,
) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


def loader(
    function: Callable[..., object] | None = None,
    /,
    *,
    depends_on: tuple[Callable[..., object], ...] | list[Callable[..., object]] = (),
    target: str | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a Python function as a SQLBuild source loader."""

    normalized_deps: tuple[Callable[..., object], ...] = tuple(depends_on)
    if function is not None:
        return _decorate_loader(function, depends_on=normalized_deps, target=target)

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        return _decorate_loader(inner, depends_on=normalized_deps, target=target)

    return decorate


def get_loader_definition(function: Callable[..., object]) -> LoaderDefinition | None:
    """Return SQLBuild loader metadata from a decorated function, if present."""

    value: Any = getattr(function, "__sqlbuild_loader__", None)
    if isinstance(value, LoaderDefinition):
        return value
    return None
