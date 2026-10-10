"""Take one resource's native fact, raising the error Python's assembly raises there."""

from __future__ import annotations

from sqlbuild.compiler.project_assembly.models import NativeProjectResources, NativeResourceFailure


def native_resource[T](
    *, resources: NativeProjectResources, slot: str, items: tuple[T, ...], index: int
) -> T:
    """Return resource `index` of `slot`, raising the error Python's assembly raises there."""

    failure: NativeResourceFailure | None = resources.failure
    if failure is not None and failure.slot == slot and failure.index == index:
        raise failure.error
    return items[index]
