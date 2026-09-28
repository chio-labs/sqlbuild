"""Dependency declaration normalization for Python-node decorators."""

from collections.abc import Callable

from sqlbuild.errors.contracts.exceptions import SharedInputError
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


def normalize_hook_reads(
    value: SqlResourceRef | tuple[SqlResourceRef, ...] | list[SqlResourceRef],
) -> tuple[SqlResourceRef, ...]:
    reads: tuple[object, ...] = (value,) if isinstance(value, SqlResourceRef) else tuple(value)
    invalid: object | None = next(
        (item for item in reads if not isinstance(item, SqlResourceRef)), None
    )
    if invalid is not None:
        raise SharedInputError(
            "@hook(reads=...) accepts model(...), source(...), and seed(...) references only; "
            f"got {type(invalid).__name__}"
        )
    return tuple(dict.fromkeys(item for item in reads if isinstance(item, SqlResourceRef)))
